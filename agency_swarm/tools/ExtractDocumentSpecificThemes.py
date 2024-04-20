import pandas as pd
from pydantic import Field
from agency_swarm import BaseTool
from agency_swarm.util import get_openai_client
import json
import requests
from PyPDF2 import PdfReader
from io import BytesIO
from tabula import read_pdf
from agency_swarm.agency.agency import shared_state
from typing import List
from openai import AzureOpenAI
import os
import tqdm


class ExtractDocumentSpecificThemes(BaseTool):
    """
    This tool extracts central themes/focus areas from documents to help understand the content of the documents better. The tool directly pulls data from the working memory and does not require any file ids.

    If Cross Document Trend Analysis or Topic Modeling is required, subsequently use the ExtractCrossDocumentTrends tool.
    """
    output_file_path: str = Field(
        "saved_documents/Document_Specific_Themes.xlsx",
        description="The path where the output Excel file will be saved. The path should be prefixed with 'saved_documents' and followed by the desired filename."
    )

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
                print("Chat Working Memory")
                print(shared_state.working_chat_memory)
                working_memory.update(shared_state.working_chat_memory)
            
            else:
                raise ValueError(f"Unsupported memory type: {memory}. Please provide either 'working_sourced_memory', 'working_upload_memory' or 'working_chat_memory' as entries of memory type.")
        
        if working_memory:
            names = []
            focus_areas = []
            contents = []

            if len(working_memory) > 1:
                for i, (_, file_path) in enumerate(working_memory.items()):

                    if file_path.endswith('.pdf'):
                        pdf = PdfReader(file_path)
                        # Extract the text from each page
                        content = "\n".join([page.extract_text() for page in pdf.pages])
                        # Extract table data
                        tables = read_pdf(file_path, pages='all', multiple_tables=True)
                        table_data = "\n\n".join([table.to_string() for table in tables])
                        content += "\n\nTable Data:\n" + table_data

                        names.append(os.path.basename(file_path))
                        contents.append(content)  

                df = pd.DataFrame({'Document Name': names, 'Content': contents})  
                row_name = 'Content'    

            else:
                df = pd.read_excel(list(working_memory.values())[0])  
                print(df)
                row_name = 'Content'

            for i, row in tqdm.tqdm(df.iterrows()):   

                sys_prompt = """You are an analyst working for a consulting firm. Your job is to read through the given content and extract all possible relevant focus areas of the document. The focus areas you generate are going to be used for further topic modeling across a set of documents. Thus the agenda is to extract focus areas that don't contain very specific terms or are very streamlined to the document under consideration and are more generalized."""

                user_prompt = f"""Content:
{row[row_name]}

Analyse the given content and extract all possibly relevant focus areas the report talks about. To keep the focus areas general and high level, extract focus areas in about 4-5 words. Extract a maximum of 5 focus areas that are most relevant from any given content.

For each of these focus area, you are to also compile a detailed `Research Note` that explains the focus area in detail based only on the report itself. Your notes should comprehensively cover details from the report for each focus area provided. These details should be in a narrative paragraph that includes quotes/sentences and detailed insights from the report.


""" + """As final output, return a JSON with two columns 'Focus Areas' and 'Notes' which contain a list of relevant descriptive focus areas the document talks about and the list of corresponding research notes for each focus area.

Expected JSON Output:
{
"Focus Areas": ["focus_area1", "focus_area2", "focus_area3",...],
"Notes": ["research_note1 based on data from report for focus_area1", "research_note2..", "research_note3..",...]
}"""

                messages = [{"role": "system", "content": sys_prompt},
                            {"role": "user", "content": user_prompt}]

                # client = get_openai_client()
                # response = client.chat.completions.create(
                #     model="gpt-4-1106-preview",
                #     messages=messages,
                #     max_tokens=1024,
                #     response_format={"type": "json_object"},
                #     temperature=0.1
                # )

                client = AzureOpenAI()
                response = client.chat.completions.create(
                    model="gpt4",
                    messages=messages,
                    temperature=0,
                    response_format={"type": "json_object"}
                )

                focus_areas = json.loads(response.choices[0].message.content)['Focus Areas']
                notes = json.loads(response.choices[0].message.content)['Notes']

            df['Focus Areas'] = focus_areas
            df['Notes'] = notes

            # Save DataFrame to Excel
            df.to_excel(self.output_file_path, index=False)
            shared_state.latest_chat_memory = {}
            shared_state.latest_chat_memory["Extracted Focus Areas"] = self.output_file_path
            print(shared_state.latest_chat_memory)

            return f"Here are the document specific themes from the first five documents\n\n {str(df.head())} \n\nThe excel file with focus areas of all files under consideration has been created and saved in `latest_chat_memory`. One Document uploaded to `latest_chat_memory`."
        else:
            return "No working memory found. Please update the relevant working memory"    
