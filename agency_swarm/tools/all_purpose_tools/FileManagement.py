from pydantic import Field
from agency_swarm import BaseTool
from agency_swarm.util import get_openai_client
import pandas as pd
from typing import List
from agency_swarm.agency.agency import shared_state
from pydantic import validator


class UpdateWorkingMemory(BaseTool):
    """
    ALWAYS CALL THIS TOO to update the working memory before invoking any agent whose tools require passing the memory_type argument beacuse otherwise the agent will either receive empty working memory or outdated working memory.
    Use this tool to update the working memory from the current memory by either including or excluding a few files. The type of working memory to be updated will depend on the memory_type argument. 
    
    If you want to include a file, you need to provide the file numbers in the files_to_include argument. For example, if you want to include the 1st, 2nd from a set of 50 files you need to provide ["1", "2"] as the input. 
    If you want to exclude a few files, you need to provide the file numbers in the files_to_exclude argument. Say out of the 50 files, you need to drop files ["5", "10", "45"] 
    
    Including and Excluding files depend on the number of files and whether its easy to include or exclude from the set. If you have 50 files and you want to include 5 files, you can provide the files_to_include. However, if you want to exclude 5 files, then instead of providing 45 inclusion files, you provide files_to_exclude with the 5 files to exclude.

    If you want to process all files, you can provide an empty list for "files_to_exclude".

    You only need to provide one argument, either files_to_include or files_to_exclude. If you provide both, the tool will raise an error. If you provide none, the tool will raise an error. You can call this too multiple times to update different working memory_types.
    """
    memory_type: str = Field(..., description="""The type of memory to analyze. It can be either 'latest_sourced_memory' or 'latest_upload_memory' or 'latest_chat_memory'.

If files were uploaded by the user, use 'latest_upload_memory'. 
If files were sourced by DataSourcing Agent, use 'latest_sourced_memory'. 
If you want to analyze the chat history, use 'latest_chat_memory'."""
                             )
    files_to_include: List = Field(
        None, description="""list of file numbers to include. for example ["1", "3", "5", "6"]"""
    )
    files_to_exclude: List = Field(
        None, description="""list of file numbers to exclude. for example ["1", "3", "5", "6"]. Provide an empty list if no file is to be excluded"""
    )
    
    @validator('files_to_include', 'files_to_exclude', pre=True)
    def check_files(cls, value, values, **kwargs):
        files_to_include = values.get('files_to_include')
        files_to_exclude = values.get('files_to_exclude')

        if 'files_to_include' in kwargs and value is not None and files_to_exclude is not None:
            raise ValueError('Only one of files_to_include or files_to_exclude can be provided.')
        if 'files_to_include' in kwargs and value is not None and files_to_exclude == []:
            raise ValueError('If you want to include all files, only provide an empty list for files_to_exclude. Keep files_to_include as None.')
        if 'files_to_exclude' in kwargs and value is None and files_to_include is None:
            raise ValueError('Either files_to_include or files_to_exclude must be provided. If you want to include all files, only provide an empty list for files_to_exclude. Keep files_to_include as None.')
        return value

    def run(self):
        if self.memory_type == "latest_sourced_memory":
            items = list(shared_state.latest_sourced_memory.items())
        elif self.memory_type == "latest_upload_memory":
            items = list(shared_state.latest_upload_memory.items())
        elif self.memory_type == "latest_chat_memory":
            items = list(shared_state.latest_chat_memory.items())
        else:
            raise ValueError("Invalid memory type. It can be either 'latest_sourced_memory' or 'latest_upload_memory' or 'latest_chat_memory'.")

        if self.files_to_include:
            included_items = [items[int(file_number) - 1] for file_number in self.files_to_include if 0 <= int(file_number) - 1 < len(items)]
            items = included_items
        elif self.files_to_exclude != []:
            for file_number in self.files_to_exclude:
                if 0 <= int(file_number) - 1 < len(items):
                    del items[int(file_number) - 1]

        if self.memory_type == "latest_sourced_memory":
            shared_state.working_sourced_memory = dict(items)
            print('Latest Sourced Memory Updated:')
            print(shared_state.working_sourced_memory)
        elif self.memory_type == "latest_upload_memory":
            print('Latest Upload Memory Updated:')
            shared_state.working_upload_memory = dict(items)
            print(shared_state.working_upload_memory)
        elif self.memory_type == "latest_chat_memory":
            shared_state.working_chat_memory = dict(items)
            print('Latest Chat Memory Updated:')
            print(shared_state.working_chat_memory)

        return f"`working{self.memory_type[6:]}` has been updated with required files."
    


class UpdateWorkingLongtermMemory(BaseTool):
    """
    All the files within the chat interaction (files sourced by the DataSourcing Agent/User uploads/Files saved in Chat History) are stored in the longterm memory. The last sourcing/file upload/saved files will be stored in their respective latest_memories. These can be accessed using the `UpdateWorkingMemory` tool.

    However, if user is requesting for some document analysis that was not past of the latest_sourcing_memory or latest_upload_memory or latest_chat_memory, then you can use this tool to retrieve the required files from the longterm memory.
    """

    user_query:str = Field(..., description="""The user query describing which files the user needs from the long-term memory for the analysis requested. Be descriptive about which files are needs since a detailed query will help in retrieving the right files from the long-term memory. 
                           
For example, if original user query is: 
'I want to use the excel document that you had created earlier from the Word Files I had uploaded. I want to classify the input entries from the excel into a new taxonomy that I will upload', 
                           
then what needs to be sent here is 
"Retrieve the excel document created earlier from the Word Files that the user had uploaded".""")

    def run(self):
        pass
