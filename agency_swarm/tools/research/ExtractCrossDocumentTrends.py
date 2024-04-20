import pandas as pd
from pydantic import Field
from agency_swarm import BaseTool
from agency_swarm.util import get_openai_client
import json
from agency_swarm.agency.agency import shared_state
from typing import List
from openai import AzureOpenAI
import tqdm
import ast


class ExtractCrossDocumentTrends(BaseTool):
    """
    Important: Before using this tool, ensure to the extract document specific themes using the `ExtractDocumnetSpecificThemes` Tool. 
    
    This tool generates standardized themes from a bunch of focus areas extracted from multiple documents. This tool is to be used to generate a trend analysis or topic modeling over multiple documents.
    """
    memory_type: List = Field(..., description="""The type of memories to analyze. It can be one or combination of 'working_sourced_memory' or 'working_upload_memory' or 'working_chat_memory'.
                             
For example,
["working_sourced_memory"] or ["working_sourced_memory", "working_chat_memory"] or ["working_chat_memory", "working_upload_memory", "working_sourced_memory"]"""
    )

    def count_documents_per_theme_with_links(self, message, themes):
        theme_document_links = {message[group]['Theme Name']: [] for group in message}

        for key, group in message.items():
            print(group['Theme Name'])
            theme_name = group['Theme Name']
            theme_focus_areas = set(list(group['Focus Areas']))

            # Iterate over each document in self.themes
            for dic in themes:
                for document_no, focus_areas in dic.items():
                    if any(focus_area in theme_focus_areas for focus_area in list(focus_areas)):
                        theme_document_links[theme_name].append(document_no)

        theme_document_count_with_links = {
            theme: {'count': len(links), 'links': links} for theme, links in theme_document_links.items()
        }

        return theme_document_count_with_links

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
        
        if not working_memory:
            working_memory ={'bn': "saved_documents/Generative_AI_Focus_Areas.xlsx"}
        if working_memory:
            df = pd.read_excel(list(working_memory.values())[0])
            themes = []

            if 'Focus Areas' not in df.columns:
                return f""""Column name 'Focus Areas' not found in the file. 
                
Possible reasons for this error:
1. You have either not used the `ExtractDocumentSpecificThemes` tool to get the focus areas first.
2. You have not used the `UpdateWorkingMemory` tool with latest_chat_memory and files_to_exclude = [] to update the correct file in working memory. Retrospect on past messages to understand what needs to be done."""
            
            for i, row in df.iterrows():
                themes.append({f"Document {i+1}": ast.literal_eval(row['Focus Areas'])})

            print(themes)        
            user_prompt = f"""Below is a list of focus areas extracted from multiple files with the file URL

Focus Areas:
{themes}

Your task is to group similar focus areas into a standardized theme by focusing on their semantic similarities. Ignore the links. 

Here are some rules to follow:
1. Generate multiple nuanced standardized themes.
1. All the standardized themes generated should be mutually exclusive but collectively exhaustive.
2. Make sure that every focus area from the given list is assigned to a standardized theme group. Not a single focus area should be skipped.

While grouping the themes, follow the below approach:
1. Think about the standardized Theme Name i.e., a common label you can name that particular group of focus areas. The name of the group should be succinct and should account for all the focus areas within it.
2. A list of focus areas from the ones mentioned above that fall under the particular group.

As final output return a list of JSONs. Each JSON should contain 2 columns `Theme Name`, `Focus Areas`. Please follow the template JSON example.
"""+ "Example output: {{'Theme Group 1': {'Theme Name': 'Appropriate Theme Name', 'Focus Areas': ['Area 1', 'Area 2',...]}}}}"


            messages = [{"role": "system", "content": "You are a topic modeling bot that always responds in JSON format"},
                        {"role": "user", "content": user_prompt}]

            # client = get_openai_client()
            # response = client.chat.completions.create(
            #     model="gpt-4-turbo-preview",
            #     messages=messages,
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
            message = json.loads(response.choices[0].message.content)
            print(message)

            try:
                insights = self.count_documents_per_theme_with_links(message, themes)

                # Save the insights in a file
                with open("saved_documents/Document_Specific_Themes_Insights.txt", "w") as f:
                    f.write(str(insights))

                shared_state.latest_chat_memory = {}
                shared_state.latest_chat_memory["Document_Specific_Themes_Insights"] = "saved_documents/Document_Specific_Themes_Insights.txt"
        

                return f"The standardized themes are as follows:\n{message}\n\n The insights containing the number of documents per theme have been saved in a file in `latest_chat_memory`. If the user requests visualization on this, please ensure that the Interface Mnaager knows to update the chat memory for the visualization"

            except Exception as e:
                print(e)
                return message
            
        else:
            return f"No files found in the working memory. Update the relevant working memory with latest documents using the 'UpdateWorkingMemory' tool for correct analysis."


# test = ExtractCrossDocumentTrends(memory_type=["working_sourced_memory"]) 
# ans = test.run()
# print(ans)
