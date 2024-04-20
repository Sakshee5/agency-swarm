import pandas as pd
from pydantic import Field
from typing import List, Tuple
from agency_swarm import BaseTool
from agency_swarm.util import get_openai_client
import json
from agency_swarm.agency.agency import shared_state
from openai import AzureOpenAI
import tqdm
import os

# class ClassifyExcelEntries(BaseTool):
#     """
#     This tool classifies entries from an input excel file into categories based on a taxonomy file. The tool directly pulls this data from the working memory and does not require any file ids. The tool populates the category labels and a justification for each classification against the input data in the excel file and saves it locally in the default or provided path.

#     The number of classification levels and the column names for each level are dynamic and are to be provided as input parameters.
#     """
#     memory_type: List = Field(..., description="""The type of memories to analyze. It can be one or combination of 'working_sourced_memory' or 'working_upload_memory' or 'working_chat_memory'.
                             
# For example,
# ["working_sourced_memory"] or ["working_sourced_memory", "working_chat_memory"] or ["working_chat_memory", "working_upload_memory", "working_sourced_memory"]"""
#     )
#     input_cols_to_consider: List[str] = Field(None,
#     description="List of input columns to consider. For example ['Job Title Name', 'Job Summary', ...]. If defauled to 'None', use all available columns."
#     )
#     level_cols: List[List[str]] = Field(...,
#         description="""A list of lists, where each sub-list represents a level and contains the column names for that level. Ask the user to provide the column names for each level.
# Only an example: for two levels --> [['column name A', 'column name B'], ['column name C', 'column name D']]

# where 'column name A', 'column name B' are level 1 columns
# and 'column name C', 'column name D' are level 2 columns.
# Donot use example column names."""
#     )
#     output_file_path: str = Field(
#         "saved_documents/classification_DataFile.xlsx", description="The path where the output Excel file will be saved. The path should be prefixed with 'saved_documents' and followed by the desired filename."
#     )

#     def run(self):
#         working_memory = {}

#         for memory in self.memory_type:
#             if memory == "working_sourced_memory":
#                 print("Sourced Working Memory")
#                 print(shared_state.working_sourced_memory)
#                 working_memory.update(shared_state.working_sourced_memory)

#             elif memory == "working_upload_memory":
#                 print("Upload Working Memory")
#                 print(shared_state.working_upload_memory)
#                 working_memory.update(shared_state.working_upload_memory)

#             elif memory == "working_chat_memory":
#                 print("Upload Chat Memory")
#                 print(shared_state.working_chat_memory)
#                 working_memory.update(shared_state.working_chat_memory)
            
#             else:
#                 raise ValueError(f"Unsupported memory type: {memory}. Please provide either 'working_sourced_memory', 'working_upload_memory' or 'working_chat_memory' as entries of memory type.")

#         # working_memory = {'xyz': 'abc'}
#         if working_memory:
#             shared_state.latest_chat_memory = {}
#             if len(working_memory) == 1:
#                 return "Working memory contains only 1 file. @ClassificationAgent: Please ensure that the memory_type argument was passed the correct memory type(s). If you think the correct memory type(S) is/ARE being passed then let @InterfaceManager know to update the relevant working memories with latest documents using the 'UpdateWorkingMemory' tool for correct analysis."
            
    #         messages = [{'role': 'user', 'content': f"""You will be provided with a dictionary with two files. One of these is the Input File and the other is the Taxonomy File. The Input File contains the data that needs to be classified and the Taxonomy File contains the categories and their definitions. Your task is to diffrentiate which is the input_file and which is taxonomy based the metadata in the dictionary keys.
                        
    # Dictionary
    # {working_memory}"""+"""

    # As final output, generate a json containing two columns. The column names should be "input_file" and, "taxonomy". 
    # Expected JSON:
    # {
    # "input_file": "local path of the input file from the value of the provided dictiornary above",
    # "taxonomy": "local path of the taxonomy file from the value of the provided dictionary"
    # }
    # Please provide the correct local path AS-IS."""}]

#             # client = get_openai_client()
#             # response = client.chat.completions.create(
#             #     model="gpt-4",
#             #     messages=messages,
#             #     max_tokens=1024,
#             #     # response_format={"type": "json_object"}
#             # )
#             # files = json.loads(response.choices[0].message.content)

#             client = AzureOpenAI()
#             response = client.chat.completions.create(
#                 model="gpt4",
#                 messages=messages,
#                 temperature=0,
#                 response_format={"type": "json_object"}
#             )

#             files = json.loads(response.choices[0].message.content)
            
#             input_file_path = files['input_file']
#             taxonomy_file_path = files['taxonomy']

#             if not self.input_cols_to_consider:
#                 input_df = pd.read_excel(input_file_path)
#             else:
#                 input_df = pd.read_excel(input_file_path)[self.input_cols_to_consider]

#             classification_level = {"classification_level_"+str(i+1): [] for i in range(len(self.level_cols))}
#             justification_level = {"justification_level_"+str(i+1): [] for i in range(len(self.level_cols))}
            
#             for i, row in tqdm.tqdm(input_df.iterrows()):
#                 taxonomy_df = pd.read_excel(taxonomy_file_path)
#                 # print(taxonomy_df.head())
#                 for level, cols in enumerate(self.level_cols):

#                     sys_prompt = """You are a Classification Expert."""
#                     user_prompt = f"""Your task is to classify each entry of the description list into one of the criteria from the list mentioned below. The given categories with be a dataframe containing a category label followed by the category definition.  Always try to fit the given entry to at least one of the criteria given. However, if the entry is not at all relevant to any of the given criteria, simply return the categories as "-".

# Description_list:
# {row}

# Criteria_list:
# {taxonomy_df[cols].drop_duplicates()}"""

#                     json_prompt = f"""As final output, generate a json containing two columns. The column names should be "Justification" and, "Prediction":
# 1. Please make sure that you consider the examples and definition for every category provided in the Categories_list before making the classification.
# 2. For every description in the description list, make sure that all the above mentioned points are considered and the classification is made
# 3. Make sure that the classification is made only from the given Categories without changing the name.
# 4. The justification given for every classification should not be more than 300 words."""

#                     messages = [
#                         {'role': 'system', 'content': sys_prompt},
#                         {'role': 'user', 'content': user_prompt + '\n\n' + json_prompt}]

#                     # client = get_openai_client()
#                     # try:
#                     #     response = client.chat.completions.create(
#                     #         model="gpt-4",
#                     #         messages=messages,
#                     #         max_tokens=1024,
#                     #         # response_format={"type": "json_object"}
#                     #     )
#                     #     message = json.loads(response.choices[0].message.content)

#                     try:
#                         response = client.chat.completions.create(
#                             model="gpt4",
#                             messages=messages,
#                             temperature=0,
#                             response_format={"type": "json_object"}
#                         )

#                         message = json.loads(response.choices[0].message.content)
#                         pred = message["Prediction"]
#                         justi = message["Justification"]
#                     except Exception as e:
#                         print(f"Error during API call: {e}")
#                         pred = "Error"
#                         justi = "Error"

#                     classification_level["classification_level_" + str(level+1)].append(pred)
#                     justification_level["justification_level_" + str(level+1)].append(justi)

#                     # Update taxonomy_df for next level
#                     if level < len(self.level_cols) - 1:
#                         taxonomy_df = taxonomy_df[taxonomy_df[cols[0]] == pred][self.level_cols[level + 1]]

#             # Add results to DataFrame
#             for level, cols in enumerate(self.level_cols):
#                 input_df[cols[0] + ' Classification'] = classification_level["classification_level_" + str(level+1)]
#                 input_df[cols[0] + ' Justification'] = justification_level["justification_level_" + str(level+1)]

#             # Save DataFrame to Excel
#             input_df.to_excel(self.output_file_path, index=False)
            
#             shared_state.latest_chat_memory["Output File From Classification"] = self.output_file_path

#             return f"The classification results excel file has been created and saved. One Document uploaded to `latest_chat_memory`."
        
#         else:
#             return f"No files found in the working memory. @Classification Agent: Please ensure that the memory_type argument was passed the correct memory type(s). If you think the correct memory type(s) is/are being passed then let @InterfaceManager know to update the relevant working memory with latest documents using the 'UpdateWorkingMemory' tool for correct analysis."


class ClassifyExcelEntries(BaseTool):
    """
    Use this tool when
    1. All the entries that need to be classified are provided in an inout excel file. Optionally, input columns to be considered can also be provided
    2. Single or Multiple taxonomy files are provided with corresponding file names as well as column names which get sent in the `level_cols` argument. 
    """
    memory_type: List = Field(..., description="""The type of memories to analyze. It can be one or combination of 'working_sourced_memory' or 'working_upload_memory' or 'working_chat_memory'.
                             
For example,
["working_sourced_memory"] or ["working_sourced_memory", "working_chat_memory"] or ["working_chat_memory", "working_upload_memory", "working_sourced_memory"]"""
    )

    input_cols_to_consider: List[str] = Field(None,
    description="List of input columns to consider. For example ['Job Title Name', 'Job Summary', ...]. If defauled to 'None', use all available columns."
    )
    taxonomy_level_cols_names: dict[str, List[List[str]]] = Field(...,
        description="""This is required argument. A dictionary of list of lists, where the dictionary key represents the taxonomy name and dictionary value list contains the columns names for multiple levels. Each sub-list contains the column names for that level. Ask the user to provide the column names for each level for each taxonomy.

Only an example: for two taxonomies. 1st with 2 levels and 2nd with 1 level --> 
{
"name of taxonomy1.xlsx": [['column name A', 'column name B'], ['column name C', 'column name D']], 
"name of taxonomy2.xlsx": [['column name W', 'column name X']],
....
}

where 'column name A', 'column name B' are level 1 columns from taxonomy 1
and 'column name C', 'column name D' are level 2 columns from taxonomy 1

'column name W', 'column name X' are level 1 columns from taxonomy 2
Donot use example column names."""
    )
    output_file_path: str = Field(
        "saved_documents/classification_DataFile.xlsx", description="appropriate path name where the output Excel file will be saved. The path should be prefixed with 'saved_documents' and followed by the desired filename."
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
            if len(working_memory) == 1:
                return "Working memory contains only 1 file. @ClassificationAgent: Please ensure that the memory_type argument was passed the correct memory type(s). If you think the correct memory type(S) is/ARE being passed then let @InterfaceManager know to update the relevant working memories with latest documents using the 'UpdateWorkingMemory' tool for correct analysis."
            
#             messages = [{'role': 'user', 'content': f"""You will be provided with a dictionary with two or more files. One of these is the Input File and the rest are Taxonomy Files. The Input File contains the data that needs to be classified and the Taxonomy Files contain the categories and their definitions. Your task is to diffrentiate which is the input_file and which is taxonomy based on the metadata in the dictionary keys.
                        
# Dictionary
# {working_memory.keys()}"""+"""

# As final output, generate a json containing a single column. The column name should be "input_file".
# Expected JSON:
# {
# "input_file": "local path of the input file from the value of the provided dictiornary above",
# }
# Please provide the correct local path AS-IS.

# Incase you think none of the files are input file, please simply return 
# {"input_file": "None"}."""}]

            # client = get_openai_client()
            # response = client.chat.completions.create(
            #     model="gpt-4",
            #     messages=messages,
            #     max_tokens=1024,
            #     # response_format={"type": "json_object"}
            # )
            # files = json.loads(response.choices[0].message.content)

            client = AzureOpenAI()
            # response = client.chat.completions.create(
            #     model="gpt4",
            #     messages=messages,
            #     temperature=0,
            #     response_format={"type": "json_object"}
            # )

            # files = json.loads(response.choices[0].message.content)
            # print(files)

            # if files['input_file'] == "None":
            #     return "None of the files are input file. Check with the Interface Manager whether the correct files are being passed and whether the memory has been updated corectly."
            
            all_files = list(working_memory.keys())
            taxonomy_files = list(self.taxonomy_level_cols_names.keys())

            
            input_file_name = list(set(all_files) - set(taxonomy_files))
            print('input_file_name:', input_file_name)

            if not input_file_name:
                return "No input file found. Check with the Interface Manager whether the correct files are being passed and whether the memory has been updated corectly."

            input_file_path = working_memory[input_file_name[0]]
            # for i in range(len(files)-1):
            #     taxonomy_file_path = files['taxonomy'+str(i+1)]
            #     taxonomy_columns = files['taxonomy'+str(i+1)+'_columns']
            #     print(taxonomy_file_path)
            #     print(taxonomy_columns)

            if not self.input_cols_to_consider:
                input_df = pd.read_excel(input_file_path)
            else:
                input_df = pd.read_excel(input_file_path)[self.input_cols_to_consider]

            for taxonomy_file_name, taxonomy_columns in self.taxonomy_level_cols_names.items():
                taxonomy_file_path = working_memory[taxonomy_file_name]
                print(f"Processing taxonomy file: {taxonomy_file_path}")
                print(f"Taxonomy columns: {taxonomy_columns}")

                classification_level = {"classification_level_"+str(i+1): [] for i in range(len(taxonomy_columns))}
                justification_level = {"justification_level_"+str(i+1): [] for i in range(len(taxonomy_columns))}

                original_taxonomy_df = pd.read_excel(taxonomy_file_path)
                for i, row in tqdm.tqdm(input_df.iterrows()):
                    print(f"Processing input row {i}")
                    taxonomy_df = original_taxonomy_df.copy()
                    # print(taxonomy_df.head())
                    for level, cols in enumerate(taxonomy_columns):
                        print(f"Processing taxonomy level {level}")

                        sys_prompt = """You are a Classification Expert."""
                        user_prompt = f"""Your task is to classify each entry of the description list into one of the criteria from the list mentioned below. The given categories with be a dataframe containing a category label followed by the category definition.  Always try to fit the given entry to at least one of the criteria given. However, if the entry is not at all relevant to any of the given criteria, simply return the categories as "-".

Description_list:
{row}

Criteria_list:
{taxonomy_df[cols].drop_duplicates()}"""

                        json_prompt = f"""As final output, generate a json containing two columns. The column names should be "Justification" and, "Prediction":
1. Please make sure that you consider the examples and definition for every category provided in the Categories_list before making the classification.
2. For every description in the description list, make sure that all the above mentioned points are considered and the classification is made
3. Make sure that the classification is made only from the given Categories without changing the name.
4. The justification given for every classification should not be more than 300 words."""

                        messages = [
                            {'role': 'system', 'content': sys_prompt},
                            {'role': 'user', 'content': user_prompt + '\n\n' + json_prompt}]

                        # client = get_openai_client()
                        # try:
                        #     response = client.chat.completions.create(
                        #         model="gpt-4",
                        #         messages=messages,
                        #         max_tokens=1024,
                        #         # response_format={"type": "json_object"}
                        #     )
                        #     message = json.loads(response.choices[0].message.content)

                        try:
                            response = client.chat.completions.create(
                                model="gpt4",
                                messages=messages,
                                temperature=0,
                                response_format={"type": "json_object"}
                            )

                            message = json.loads(response.choices[0].message.content)
                            pred = message["Prediction"]
                            justi = message["Justification"]
                        except Exception as e:
                            print(f"Error during API call: {e}")
                            pred = "Error"
                            justi = "Error"

                        classification_level["classification_level_" + str(level+1)].append(pred)
                        justification_level["justification_level_" + str(level+1)].append(justi)

                        # Update taxonomy_df for next level
                        if level < len(taxonomy_columns) - 1:
                            taxonomy_df = taxonomy_df[taxonomy_df[cols[0]] == pred][taxonomy_columns[level + 1]]
                            print(f"Updated taxonomy_df for next level: {taxonomy_df}")

                        print(f"Prediction: {pred}")
                        print(f"Justification: {justi}")

                # Add results to DataFrame
                for level, cols in enumerate(taxonomy_columns):
                    print(f"Adding results to DataFrame for taxonomy level {level}")
                    input_df[cols[0] + ' Classification ' + os.path.basename(taxonomy_file_path)] = classification_level["classification_level_" + str(level+1)]
                    input_df[cols[0] + ' Justification ' + os.path.basename(taxonomy_file_path)] = justification_level["justification_level_" + str(level+1)]
                    print(input_df)

            # Save DataFrame to Excel
            input_df.to_excel(self.output_file_path, index=False)
            
            shared_state.latest_chat_memory = {}
            shared_state.latest_chat_memory["Output File From Classification"] = self.output_file_path

            return f"The classification results excel file has been created and saved. One Document uploaded to `latest_chat_memory`."
        
        else:
            return f"No files found in the working memory. @Classification Agent: Please ensure that the memory_type argument was passed the correct memory type(s). If you think the correct memory type(s) is/are being passed then let @InterfaceManager know to update the relevant working memory with latest documents using the 'UpdateWorkingMemory' tool for correct analysis."
