import pandas as pd
from pydantic import Field
from agency_swarm import BaseTool
from agency_swarm.util import get_openai_client
import json
import requests
from PyPDF2 import PdfReader
from io import BytesIO
import numpy as np
from scipy import spatial
import tiktoken
from agency_swarm.agency.agency import shared_state
from typing import List


def get_embedding(text):
    client = get_openai_client()
    response = client.embeddings.create(
        input=text,
        model="text-embedding-ada-002"
    )

    return response.data[0].embedding


def cosine_similarity(a, b):
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))


def distances_from_embeddings(
        query_embedding,
        embeddings,
        distance_metric="cosine"):
    """Return the distances between a query embedding and a list of embeddings."""
    distance_metrics = {
        "cosine": spatial.distance.cosine,
        "L1": spatial.distance.cityblock,
        "L2": spatial.distance.euclidean,
        "Linf": spatial.distance.chebyshev,
    }
    distances = [
        distance_metrics[distance_metric](query_embedding, embedding)
        for embedding in embeddings
    ]
    return distances


def get_token_cl100k(inp):
    cl100k_base = tiktoken.get_encoding("cl100k_base")
    enc = tiktoken.Encoding(
            name="chat-davinci-003",
            pat_str=cl100k_base._pat_str,
            mergeable_ranks=cl100k_base._mergeable_ranks,
            special_tokens={
                **cl100k_base._special_tokens,
                "<|im_start|>": 100264,
                "<|im_end|>": 100265,
                "<|im_sep|>": 100266,
            }
        )
    tokens = enc.encode(inp, allowed_special={"<|im_start|>", "<|im_end|>"})
    return tokens


class QAContent(BaseTool):
    """
    This tool is capable of analzing/querying the content from multiple documents and answering user queries about the same. Use when the user needs explanation, answers to specific question from content.

    The tool directly pulls data from the working memory and does not require any file ids.
    """
    user_query: str = Field(..., description="Complete user query. provide all requested asks here since this query will be used to generate the response. you can also include multiple sentences.")

    memory_type: List = Field(..., description="""The type of memories to analyze. It can be one or combination of 'working_sourced_memory' or 'working_upload_memory' or 'working_chat_memory'.
                             
For example,
["working_sourced_memory"] or ["working_sourced_memory", "working_chat_memory"] or ["working_chat_memory", "working_upload_memory", "working_sourced_memory"]"""
    )

    def run(self):

        working_memory = {}

        for memory in self.memory_type:
            if memory == "working_sourced_memory":
                print("Sourced Working Memory")
                print(shared_state.working_sourced_memory)
                working_memory.update(shared_state.working_sourced_memory)

            elif memory == "working_upload_memory":
                print("Upload Working Memory")
                print(shared_state.working_upload_memory)
                working_memory.update(shared_state.working_upload_memory)

            elif memory == "working_chat_memory":
                print("Upload Chat Memory")
                print(shared_state.working_chat_memory)
                working_memory.update(shared_state.working_chat_memory)
            
            else:
                raise ValueError(f"Unsupported memory type: {memory}. Please provide either 'working_sourced_memory', 'working_upload_memory' or 'working_chat_memory' as entries of memory type.")
        
        if working_memory:
            rows = []
            for i, (_, file_path) in enumerate(working_memory.items()):
                pdf_reader = PdfReader(file_path)

                for no, page in enumerate(pdf_reader.pages):
                    content = page.extract_text()
                    embedding = get_embedding(content)
                    n_tokens = len(get_token_cl100k(content))
                    rows.append({
                        "local_file_path": file_path,
                        "page_num": no,
                        "content": content,
                        "embedding": embedding,
                        "n_tokens": n_tokens
                    })

            df = pd.DataFrame(rows)

            dummy_csv = "text, source,\n"
            q_embedding = get_embedding(self.user_query)
            df["distance"] = distances_from_embeddings(q_embedding, df["embedding"].values, distance_metric="cosine")
            current_len = 0
            max_len = 5000

            for idx, row in df.sort_values("distance", ascending=True).iterrows():
                current_len += row["n_tokens"] + 2
                if current_len > max_len:
                    break
                dummy_csv += "\"{}\", \"{}_{}\"\n".format(str(row["content"]), str(row["link"]), str(row["page_num"]))

            user_prompt = f"""Answer the users query only based on the content provided.

    User Query:
    {self.user_query}

    Content:
    {dummy_csv}
    """

            messages = [{"role": "system", "content": "You are an expert Question-Answering Bot"},
                        {"role": "user", "content": user_prompt}]

            client = get_openai_client()
            response = client.chat.completions.create(
                model="gpt-4",
                messages=messages,
                max_tokens=1024,
                temperature=0.1
            )

            message = response.choices[0].message.content

            if len(message) > 1000:
                shared_state.latest_chat_memory = {}
                shared_state.latest_chat_memory[self.user_query] = message
                return message + "\n\nThe response has been saved in the latest_chat_memory since it was long. One Document uploaded to `latest_chat_memory`. Please use `UpdateWorkingMemorybyIncludingFiles` with files_to_include = ['1'] to retrieve the file is working_chat_memory for any further analysis."

            else:
                return message
            
        else:
            return "No working memory available. Please update the relevant working memory."

          
# qa_tool = QAContent(links=['https://arxiv.org/pdf/2301.01233v2.pdf'], user_query="how does the convolutional long short-term memory network model predict market price fluctuations, and what data inputs does it require?")
# answer = qa_tool.run()
# print(answer)
