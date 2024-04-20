from pydantic import Field
from agency_swarm import BaseTool
from agency_swarm.util import get_openai_client
import pandas as pd
from typing import List
from pydantic import validator
from openai import AzureOpenAI
import os
import json
from agency_swarm.agency.agency import shared_state

class SaveWorkflow(BaseTool):
    """
    Call this tool when the user wants to save the workflow for future use.
    """
    workflow_name: str = Field(..., description="""The name the user wants to give to the workflow.""")
    
    def run(self):
        sys_message = f"""Agent Swarm: Is a collection of LLM agents responsible for coordinating and collaborating to solve user requests. It's a system where users interact with an "Interface Manager" agent via a chat interface. This Interface Manager coordinates with other agents to fulfill user requests through a series of steps and instructions. This interaction has been provided to you below. The interaction of Interface Manager with internal agents is not included to keep things simple.
-----------------------------
{shared_state.workflow_thread_interaction}"""
        
        user_message = """After an initial detailed interaction, users might want to repeat the same process with different inputs, without going through the hassle of providing detailed instructions again.

To address this, we propose saving these detailed interactions as reusable workflows. These workflows will encapsulate the steps, decisions, and instructions from the initial interaction, allowing for the same tasks to be executed in the future with minimal user input.

Your task here is to capture the essence of the interaction, especially the final user decisions, and translating this into a set of direct, intent-confirming questions/statements. They should essentially bypass the need for repetitive clarifications and directly confirm the user's intent based on the previously established parameters.

Now the agent responsible for executing this workflow is only going to have access to the questions/statements you provide here. For it to be able to replicate the workflow, it will need very clear context on how things were decided during the initial interaction. For example, the file names, file paths, what files were used during analysis or other user inputs that were confirmed during the initial interaction with names.
The workflows should be designed to replicate the initial interaction as closely as possible, focusing on the final instructions and decisions made by the user.

As final output return a JSON with a two columns "workflow" and "description. You can prefix each question with "type_of_request" to ensure that a single question is presented for one type of request. For example, say for a "summarization" related query, they might be 3 back and forth's between the user and interface manager during the initial interaction or there may be some erros faced and resolved, so while replicating the workflow, the final decision should be asked about for "type_of_request" being say "summarization". Ignore the request about "saving workflows" if found.

{
"workflow": [
"type_of_request: Please ensure that the questions/statements replicate the essence of the initial interaction, focusing on the final steps and decisions made by the user. Include any specific details that were confirmed during the initial interaction, such as file names, file paths, or other user inputs.",
"type_of_request: The questions/statements should be direct and specific, aimed at confirming the user's intent without revisiting the entire clarifying dialogue from the initial interaction. For example, if a specific file or data field was confirmed during the initial interaction, the question should directly ask if the same file or data field should be used again, or if a new one is required. The goal is to bypass the need for repetitive clarifications and directly confirm the user's intent based on the previously established parameters.",
"type_of_request: For each question, ensure it's clear which files are to be used. This could be files saved in chat history, files uploaded by the user, or files sourced by the DataSourcingAgent or a combination of these. There should be complete clarity about the files to use for each type of request. Note that you can't just say 'I will use the previous file' since you don't have access to it. The file will need to be re-uploaded, re-sourced, or re-saved in chat to be usable so ensure you have clarity on what you need from the user.",
"type_of_request: Ensure that each question/statement is about one functionality each and does not ask for clarifications. The questions/statements should be designed to confirm the user's intent directly, based on the decisions made during the initial interaction."
],
"description: "high level 2 to 3 lines of decsription of what the workflow is."
}"""
        messages = [{'role': 'system', 'content': sys_message},
                    {'role': 'user', 'content': user_message}]
        
        client = AzureOpenAI()
        response = client.chat.completions.create(
            model="gpt4",
            messages=messages,
            temperature=0.15,
            response_format={"type": "json_object"}
        )

        ans = response.choices[0].message.content

        with open(f"saved_workflows/{self.workflow_name}.json", "w") as f:
            f.write(ans)

        return f"Workflow {self.workflow_name} has been saved."

class DisplayAvailableWorkflows(BaseTool):
    """
    Call this tool when the user starts interaction. This tool will display the available workflows to the user to choose from.
    """
    def run(self):
        # display the json file names from the saved_workflows folder
        if os.listdir("saved_workflows"):
            available_workflows = ""
            for i, file in enumerate(os.listdir("saved_workflows")):
                with open(f"saved_workflows/{file}", "r") as f:
                    desc = json.loads(f.read())['description']

                available_workflows += f"{i+1}. {os.path.basename(file)}: {desc}\n"

            return "The available workflows are: \n" + available_workflows
        else:
            return "No workflows available. Please interact and save a workflow before trying to select an existing workflow."

class SelectExistingWorkflow(BaseTool):
    """
    Call this tool when the user wants to select an existing workflow to execute.
    """
    workflow_name: str = Field(..., description="""The exact name of the workflow the user is requesting to be executed.""")
    
    def run(self):
        if os.listdir("saved_workflows"):
            try:
                try:
                    print("Trying to open json file")
                    with open(f"saved_workflows/{self.workflow_name}.json", "r") as f:
                        workflow = json.loads(f.read())['workflow']
                except:
                    with open(f"saved_workflows/{self.workflow_name}", "r") as f:
                        workflow = json.loads(f.read())['workflow']

                # return a list of steps : Step 1, Step 2 depending on the length of the workflow
                steps = ""
                for i in range(len(workflow)):
                    steps += f"Step {i+1}: {workflow[i]}\n"


                return f"Here are the questions you can pose the user one by one to replicate the workflow\n\n{steps}"
                 
            except KeyError:
                return "Invalid workflow name. Please select from the available workflows."
        else:
            return "No workflows available. Please interact and save a workflow before."
        


# test = SaveWorkflow(workflow_name="test")
# test.run()

# test2 = DisplayAvailableWorkflows()
# print(test2.run())
        
# test3 = SelectExistingWorkflow(workflow_name="test")
# print(test3.run())
