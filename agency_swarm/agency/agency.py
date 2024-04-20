import inspect
import json
import os
import re
import uuid
from enum import Enum
from typing import List, TypedDict, Callable, Any, Dict, Literal
from pathlib import Path
from pydantic import Field, field_validator
from rich.console import Console

from agency_swarm.agents import Agent
from agency_swarm.threads import Thread
from agency_swarm.tools import BaseTool
from agency_swarm.user import User

console = Console()

class SharedState:
    def __init__(self):
        # uploads by user
        self.previous_upload_memory = {}
        self.latest_upload_memory = {}
        self.working_upload_memory = {}

        # files curated by DataSourcingAgent
        self.latest_sourced_memory = {}
        self.working_sourced_memory = {}

        # files saved in chat history
        self.latest_chat_memory = {} 
        self.working_chat_memory = {}

        # all memory consolidated
        self.longterm_memory = {}  ## WIP - needs some metadata to be useful
        self.working_longterm_memory = {} 

        self.workflow_thread_interaction = ""
        self.succinct_backend_workings = []
        self.user_input = False
        self.display_all = True
        self.download_filepath = ""

shared_state = SharedState()

class SettingsCallbacks(TypedDict):
    load: Callable[[], List[Dict]]
    save: Callable[[List[Dict]], Any]


class ThreadsCallbacks(TypedDict):
    load: Callable[[], Dict]
    save: Callable[[Dict], Any]


class Agency:
    ThreadType = Thread
    send_message_tool_description = """Use this tool to facilitate direct, synchronous communication between specialized agents within your agency. When you send a message using this tool, you receive a response exclusively from the designated recipient agent. To continue the dialogue, invoke this tool again with the desired recipient agent and your follow-up message. Remember, communication here is synchronous; the recipient agent won't perform any tasks post-response. You are responsible for relaying the recipient agent's responses back to the user, as the user does not have direct access to these replies. Keep engaging with the tool for continuous interaction until the task is fully resolved."""
    send_message_tool_description_async = """Use this tool for asynchronous communication with other agents within your agency. Initiate tasks by messaging, and check status and responses later with the 'GetResponse' tool. Relay responses to the user, who instructs on status checks. Continue until task completion."""

    def __init__(self,
                 agency_chart: List,
                 shared_instructions: str = "",
                 shared_files: List = None,
                 async_mode: Literal['threading'] = None,
                 settings_path: str = "./settings.json",
                 settings_callbacks: SettingsCallbacks = None,
                 threads_callbacks: ThreadsCallbacks = None):
        """
        Initializes the Agency object, setting up agents, threads, and core functionalities.

        Parameters:
            agency_chart: The structure defining the hierarchy and interaction of agents within the agency.
            shared_instructions (str, optional): A path to a file containing shared instructions for all agents. Defaults to an empty string.
            shared_files (list, optional): A list of folder paths with files containing shared resources for all agents. Defaults to an empty list.
            async_mode (str, optional): The mode for asynchronous message processing. Defaults to None.
            settings_path (str, optional): The path to the settings file for the agency. Must be json. If file does not exist, it will be created. Defaults to None.
            settings_callbacks (SettingsCallbacks, optional): A dictionary containing functions to load and save settings for the agency. The keys must be "load" and "save". Both values must be defined. Defaults to None.
            threads_callbacks (ThreadsCallbacks, optional): A dictionary containing functions to load and save threads for the agency. The keys must be "load" and "save". Both values must be defined. Defaults to None.

        This constructor initializes various components of the Agency, including CEO, agents, threads, and user interactions. It parses the agency chart to set up the organizational structure and initializes the messaging tools, agents, and threads necessary for the operation of the agency. Additionally, it prepares a main thread for user interactions.
        """
        self.async_mode = async_mode
        if self.async_mode == "threading":
            from agency_swarm.threads.thread_async import ThreadAsync
            self.ThreadType = ThreadAsync

        self.ceo = None

        # all agents
        self.agents = []

        """to store agent id and corresponding thread id
        {"agent_name": {"recipient_agent_name": {"agent": "agent_name", "recipient_agent": "recipient_agent_name", "thread_id": "thread_id"}}}
        {
            "Interface Manager": {
                "Workflow Manager": {
                    "agent": "Interface Manager",
                    "recipient_agent": "Workflow Manager",
                    "thread": <Thread object between Interface Manager and Workflow Manager>
                },
                "Summarizer": {
                    "agent": "Interface Manager",
                    "recipient_agent": "Summarizer",
                    "thread": <Thread object between Interface Manager and Summarizer>
                },
                ...
            },
            ...
        }
        When an agent needs to send a message to another agent, it retrieves the appropriate `Thread` object from this dictionary and uses it to send the message using the `SendMessage` tool. The `Thread` object handles the communication with the OpenAI API and manages the conversation history for that pair of agents.

        1. The user sends a message to the Interface Manager in `thread1` (the thread between the user and the Interface Manager).

        2. The Interface Manager receives the message and determines that it needs to delegate a task to the Summarizer agent. 

        3. The Interface Manager uses its `SendMessage` tool to send a message to the Summarizer. This message is sent in `thread2` (the thread between the Interface Manager and the Summarizer).

        4. The Summarizer receives the message in `thread2`, performs the task, and sends a response back to the Interface Manager in `thread2`.

        5. The Interface Manager receives the response from the Summarizer in `thread2`.

        6. The Interface Manager then sends a message to the user in `thread1`, including the information it received from the Summarizer."""
        self.agents_and_threads = {}


        # agents that can interact with the user
        self.main_recipients = []

        self.recipient_agents = None
        self.shared_files = shared_files if shared_files else []
        self.settings_path = settings_path
        self.settings_callbacks = settings_callbacks
        self.threads_callbacks = threads_callbacks
        self.image_path = None

        if os.path.isfile(os.path.join(self.get_class_folder_path(), shared_instructions)):
            self._read_instructions(os.path.join(self.get_class_folder_path(), shared_instructions))
        elif os.path.isfile(shared_instructions):
            self._read_instructions(shared_instructions)
        else:
            self.shared_instructions = shared_instructions

        self._parse_agency_chart(agency_chart)
        self._create_special_tools()
        self._init_agents()
        self._init_threads()

        self.user = User()
        self.main_thread = Thread(self.user, self.ceo)

    def get_completion(self, message: str, message_files=None, yield_messages=True, recipient_agent=None):
        """
        Retrieves the completion for a given message from the main thread.

        Parameters:
            message (str): The message for which completion is to be retrieved.
            message_files (list, optional): A list of file ids to be sent as attachments with the message. Defaults to None.
            yield_messages (bool, optional): Flag to determine if intermediate messages should be yielded. Defaults to True.
            recipient_agent (Agent, optional): The agent to which the message should be sent. Defaults to the first agent in the agency chart.

        Returns:
            Generator or final response: Depending on the 'yield_messages' flag, this method returns either a generator yielding intermediate messages or the final response from the main thread.
        """
        gen = self.main_thread.get_completion(message=message, message_files=message_files,
                                              yield_messages=yield_messages, recipient_agent=recipient_agent)

        if not yield_messages:
            while True:
                try:
                    # The generator is advanced to the next message
                    next(gen)
                except StopIteration as e:
                    return e.value

        return gen

    def demo_gradio(self, height=400, dark_mode=True, share=False):
        """
        Launches a Gradio-based demo interface for the agency chatbot.

        Parameters:
            height (int, optional): The height of the chatbot widget in the Gradio interface. Default is 600.
            dark_mode (bool, optional): Flag to determine if the interface should be displayed in dark mode. Default is True.
            share (bool, optional): Flag to determine if the interface should be shared publicly. Default is False.
        This method sets up and runs a Gradio interface, allowing users to interact with the agency's chatbot. It includes a text input for the user's messages and a chatbot interface for displaying the conversation. The method handles user input and chatbot responses, updating the interface dynamically.
        """
        try:
            import gradio as gr
        except ImportError:
            raise Exception("Please install gradio: pip install gradio")

        # JavaScript code to set the theme of the Gradio interface
        js = """function () {
          gradioURL = window.location.href
          if (!gradioURL.endsWith('?__theme={theme}')) {
            window.location.replace(gradioURL + '?__theme={theme}');
          }
        }"""

        if dark_mode:
            js = js.replace("{theme}", "dark")
        else:
            js = js.replace("{theme}", "light")

        # retrieves the names of the main recipient agents and sets the first one as the default recipient
        # main_recipients are all agents that the user can directly interact with
        recipient_agents = [agent.name for agent in self.main_recipients]
        recipient_agent = self.main_recipients[0]

        # def check_file():
        #     name = Path(shared_state.download_filepath).name
        #     if name:
        #         return [gr.Button(visible=False), gr.DownloadButton(label=f"Download {name}", value=shared_state.download_filepath, visible=True)]
        #     else:
        #         return [gr.Button(visible=True), gr.DownloadButton(visible=False)]

        # def download_file():
        #     return [gr.Button(visible=True), gr.DownloadButton(visible=False)]


        with gr.Blocks(js=js) as demo:
            # creates a chatbot widget with a specified height. This widget will display the conversation between the user and the chatbot.
            chatbot = gr.Chatbot(height=height)
            with gr.Row():
                with gr.Column(scale=9):
                    # for download button
                    # c = gr.Button("Click to Download! (if a file was saved in chat)")
                    # d = gr.DownloadButton("Download", visible=False)

                    # creates a dropdown widget to select one of the main_recipient_agent for the message
                    # for UI, we will need two seperate tabs, one for interface manager and one for workflow manager
                    dropdown = gr.Dropdown(label="Recipient Agent", choices=recipient_agents,
                                           value=recipient_agent.name)
                    
                    # textbox for user message
                    msg = gr.Textbox(label="Your Message", lines=4)
                # file upload widget
                with gr.Column(scale=1):
                    file_upload = gr.Files(label="Files", type="filepath")
            button = gr.Button(value="Send", variant="primary")

            def handle_dropdown_change(selected_option):
                """This function is called when the user selects a different recipient agent from the dropdown. It updates the `recipient_agent` variable"""
                nonlocal recipient_agent
                recipient_agent = self.get_agent_by_name(selected_option)

            def handle_file_upload(file_list):
                """This function is called when the user uploads a file. It should handle the file upload and return a message indicating whether the upload was successful. Currently all files uploaded are stored in the `latest_upload_memory` dictionary which is accessible to all agents and defined in the shared_state object. Whenever a file is uploaded to gradio, it is stored in a temporary local folder and the the path and filename is what we store in this dictionary. """
                if file_list:
                    temp_latest_upload_memory = {}
                    try:
                        for file_obj in file_list:
                            if file_obj in shared_state.latest_upload_memory.values():
                                name = list(shared_state.latest_upload_memory.keys())[list(shared_state.latest_upload_memory.values()).index(file_obj)]
                                temp_latest_upload_memory[name] = file_obj
                                print(f"Existing file name: {name}")
                            else:
                                # with open(file_obj.name, 'rb') as f:
                                #     # Upload the file to OpenAI
                                #     file = self.main_thread.client.files.create(
                                #         file=f,
                                #         purpose="assistants"
                                #     )
                                temp_latest_upload_memory[os.path.basename(file_obj)] = file_obj 
                                print(f"Uploaded file name: {os.path.basename(file_obj)}")

                        # Update the current file objects
                        shared_state.latest_upload_memory = temp_latest_upload_memory

                        return list(shared_state.latest_upload_memory.keys())
                    except Exception as e:
                        print(f"Error: {e}")
                        return str(e)

                return "No files uploaded"

            def user(user_message, history):
                """This function is called when the enters a message and clicks the send button. It processes the user message, appends it to the chat history. history is a list of tuples where each tuple contains the user message and the corresponding chatbot response. The function returns the user message and the updated chat history. chat history is stored so that it can be displayed in the chatbot widget."""

                # `history` variable is used to keep track of the conversation between the user and the chatbot. It's a list of lists, where each inner list contains two elements: the user's message and the chatbot's response.
                if history is None:
                    history = []

                original_user_message = user_message

                # Append the user message with a placeholder for bot response
                if recipient_agent:
                    user_message = f"👤 User 🗣️ @{recipient_agent.name}:\n" + user_message.strip()
                else:
                    user_message = f"👤 User:" + user_message.strip()
                
                # Check if latest_upload_memory has been updated
                if shared_state.latest_upload_memory != shared_state.previous_upload_memory:
                    user_message += "\n\n📎 Attached:\n" + str(len(shared_state.latest_upload_memory.values())) + " File(s). Succesfully Uploaded."
                    # Update previous state
                    shared_state.previous_upload_memory = shared_state.latest_upload_memory.copy()

                # Check if the recipient agent is the Interface Manager so as to save the workflow thread interaction which will then be used to create a workflow
                if recipient_agent.name.lower() == "interface manager":
                    shared_state.workflow_thread_interaction += "\n\n" + user_message
                
                shared_state.user_input = True
                return original_user_message, history + [[user_message, None]]

            def bot(original_message, history):
                """This function is called after the `user` function. It should handle the bot's response to the user's message."""
                nonlocal recipient_agent
                
                # `get_completion` is called on the `main_thread` object, passing in the user's message and the recipient agent. This starts a conversation with the OpenAI API.
                gen = self.get_completion(message=original_message, message_files=[], recipient_agent=recipient_agent)

                # If the generator has a message to yield (i.e., a message has been received from the OpenAI API), it is yielded and the loop continues
                # If the generator does not have a message to yield (i.e., the conversation with the OpenAI API has ended), it raises a `StopIteration` exception.
                try:
                    # The `get_completion` method returns a generator that yields messages as they are received from the OpenAI API. This generator is stored in the `gen` variable in the `bot` function.
                    for bot_message in gen:
                        if bot_message.sender_name.lower() == "user":
                            continue

                        message = bot_message.get_sender_emoji() + " " + bot_message.get_formatted_content()

                        #############
                        # FOR SAVING WORKFLOW
                        #############
                        if bot_message.sender_name.lower() == "interface manager" and bot_message.receiver_name.lower() == "user":
                            if "Executing Function" not in message:
                                shared_state.workflow_thread_interaction += "\n\n" + f"👤 {bot_message.sender_name} 🗣️ {bot_message.receiver_name}:\n"+ bot_message.content

                                print("Workflow Thread:\n", shared_state.workflow_thread_interaction)

                        #############
                        # FOR DISPLAYING CHARTS
                        #############
                        if "local file path" in message:
                            path = ''
                            paths = re.findall(r'(\S+?\.\w+)', message)
                            for p in paths:
                                possible_path = p.strip()
                                if os.path.exists(possible_path):
                                    path = possible_path
                                    print('found', path)
                                    break
                            print("REGEX PATH FOUND ", path)
                            self.image_path = path

                        if self.image_path:
                            sender = bot_message.sender_name.lower()
                            receiver = bot_message.receiver_name.lower()
                            if sender == "graphvisualizer" and receiver == "executing function":
                                message += "\n\nIt has been arranged for the graph to be displayed. You can just tell the Interface Manager that it is AS displayed.."
                                if shared_state.display_all:
                                    history.append((None, message))
                                else:
                                    shared_state.succinct_backend_workings.append(message)
                                    history[-1] = (None, message)

                            elif sender == "visualizationagent" and receiver == "interface manager":
                                message += "\n\nThe graph is as displayed below.."
                                if shared_state.display_all:
                                    history.append((None, message))
                                    history.append((None, (self.image_path,)))
                                else:
                                    shared_state.succinct_backend_workings.append(message)
                                    shared_state.succinct_backend_workings.append(self.image_path)
                                    history[-1] = (None, message)
                                    history[-1] =(None, (self.image_path,))

                            elif sender == "interface manager" and receiver == "user":
                                if not shared_state.display_all:
                                    final_message = f"Agent Interactions: {len(shared_state.succinct_backend_workings)} messages"
                                    history[-1] = (None,  f'<span style="color: rgba(211, 211, 211, 0.5);">{final_message}</span>')
                                    shared_state.succinct_backend_workings = []
                                message += "\n\nThe graph is as displayed below.."
                                history.append((None, message))
                                history.append((None, (self.image_path,)))
                                self.image_path = None

                            elif sender == "visualizationagent" and receiver == "workflow manager":
                                message += "\n\nThe graph is as displayed below.."
                                if shared_state.display_all:
                                    history.append((None, message))
                                    history.append((None, (self.image_path,)))
                                else:
                                    shared_state.succinct_backend_workings.append(message)
                                    shared_state.succinct_backend_workings.append(self.image_path)
                                    history[-1] = (None, message)
                                    history[-1] =(None, (self.image_path,))

                            elif sender == "workflow manager" and receiver == "user":
                                if not shared_state.display_all:
                                    final_message = f"Agent Interactions: {len(shared_state.succinct_backend_workings)} messages"
                                    history[-1] = (None,  f'<span style="color: rgba(211, 211, 211, 0.5);">{final_message}</span>')
                                    shared_state.succinct_backend_workings = []

                                message += "\n\nThe graph is as displayed below.."
                                history.append((None, message))
                                history.append((None, (self.image_path,)))
                                self.image_path = None

                            else:
                                pass

                        else:
                            if shared_state.display_all:
                                # Display everything on Screen
                                history.append((None, message))
                            else:

                                # if bot_message.sender_name == "User" and "Executing Function" not in message:
                                if shared_state.user_input:
                                    placeholder_message = "Processing..."
                                    history.append((None, f'<span style="color: rgba(211, 211, 211, 0.5);">{placeholder_message}</span>'))
                                    shared_state.user_input = False

                                elif bot_message.sender_name == "Interface Manager" and bot_message.receiver_name == "User" and "Executing Function" not in message:
                                    final_message = f"Agent Interactions: {len(shared_state.succinct_backend_workings)} messages"
                                    history[-1] = (None,  f'<span style="color: rgba(211, 211, 211, 0.5);">{final_message}</span>')
                                    shared_state.succinct_backend_workings = []
                                    history.append((None, message))

                                else:
                                    high_level_working = ""

                                    if bot_message.sender_name == "Interface Manager":
                                        high_level_working = f"`{bot_message.sender_name}` is interacting with `{bot_message.receiver_name}`..."

                                    if "Interface Manager" in message and "Executing Function" in message:
                                        high_level_working = ""

                                    if "Workflow Manager" in message and "Executing Function" in message:
                                        high_level_working = ""

                                    if bot_message.receiver_name == "Interface Manager":
                                        high_level_working = f"`{bot_message.sender_name}` has returned back to `{bot_message.receiver_name}` with an update..."

                                    if "Interface Manager" not in message and "Executing Function" in message:
                                        match = re.search(r"name='(.*?)'", message)
                                        if match:
                                            high_level_working = f"`{bot_message.sender_name}` is trying to use the `{match.group(1)}` tool..."

                                    if "Workflow Manager" not in message and "Executing Function" in message:
                                        match = re.search(r"name='(.*?)'", message)
                                        if match:
                                            high_level_working = f"`{bot_message.sender_name}` is trying to use the `{match.group(1)}` tool..."

                                    # dealing with tool output
                                    if "Function Output" in message:
                                        high_level_working = f"The tool `{bot_message.sender_name}` has returned an output..."


                                    if high_level_working:
                                        shared_state.succinct_backend_workings.append(high_level_working)
                                        history[-1] = (None, f'<span style="color: rgba(211, 211, 211, 0.5);">{high_level_working}</span>')

                                    else:
                                        pass
                        # `yield` statement is used here to allow for real-time updates of the chat interface. This means that as soon as a new message is added to the `history`, the chat interface is updated to display that message, even if the `bot` function is still running and generating more messages.
                        yield "", history

                except StopIteration:
                    # Handle the end of the conversation if necessary

                    pass
            
            # sets up event handlers for the button click, dropdown change, file upload, and textbox submit events. These handlers call the appropriate functions 
                
            # Set the button's click event to call the 'user' function
            button.click(
                user,
                inputs=[msg, chatbot],
                outputs=[msg, chatbot]
            ).then(
            # After the 'user' function, call the 'bot' function
                bot, [msg, chatbot], [msg, chatbot]
            )
            # Set the dropdown's change event to call the 'handle_dropdown_change' function
            dropdown.change(handle_dropdown_change, dropdown)
            # Set the file upload's change event to call the 'handle_file_upload' function
            file_upload.change(handle_file_upload, file_upload)
            # Set the textbox's submit event to call the 'user' function
            
            # c.click(check_file, None, [c, d])
            # d.click(download_file, None, [c, d])

            msg.submit(user, 
                       [msg, chatbot], 
                       [msg, chatbot], 
                       queue=False).then(
                bot, [msg, chatbot], [msg, chatbot]
            )

            # Enable queuing for streaming intermediate outputs
            demo.queue()

        # Launch the demo
        demo.launch(share=share)
        return demo
    

    def handle_interaction_mode(self, workflow):
            """Handle whether to build a new workflow or continue with the existing one."""
            if workflow:
                return self.main_recipients[1]
            else:
                return self.main_recipients[0]
            

    def handle_file_upload(self, file_list):
        if file_list:
            temp_latest_upload_memory = {}
            try:
                for file_obj in file_list:
                    if file_obj in shared_state.latest_upload_memory.values():
                        name = list(shared_state.latest_upload_memory.keys())[list(shared_state.latest_upload_memory.values()).index(file_obj)]
                        temp_latest_upload_memory[name] = file_obj
                        print(f"Existing file name: {name}")
                    else:
                        temp_latest_upload_memory[os.path.basename(file_obj)] = file_obj 
                        print(f"Uploaded file name: {os.path.basename(file_obj)}")

                shared_state.latest_upload_memory = temp_latest_upload_memory

                return list(shared_state.latest_upload_memory.keys())
            except Exception as e:
                print(f"Error: {e}")
                return str(e)

        return "No files uploaded"
    

    def user_input(self, user_message, history, workflow):
        if history is None:
            history = []

        recipient_agent = self.handle_interaction_mode(workflow)

        # Append the user message with a placeholder for bot response
        if recipient_agent:
            user_message = f"👤 User 🗣️ @{recipient_agent.name}:\n" + user_message.strip()
        else:
            user_message = f"👤 User:" + user_message.strip()
        
        # Check if latest_upload_memory has been updated
        if shared_state.latest_upload_memory != shared_state.previous_upload_memory:
            user_message += "\n\n📎 Attached:\n" + str(len(shared_state.latest_upload_memory.values())) + " File(s). Succesfully Uploaded."
            # Update previous state
            shared_state.previous_upload_memory = shared_state.latest_upload_memory.copy()

        # Check if the recipient agent is the Interface Manager so as to save the workflow thread interaction which will then be used to create a workflow
        if recipient_agent.name.lower() == "interface manager":
            shared_state.workflow_thread_interaction += "\n\n" + user_message
        
        shared_state.user_input = True
        return history + [[user_message, None]]

    def bot_output(self, original_message, history, workflow):
        recipient_agent = self.handle_interaction_mode(workflow)
        
        gen = self.get_completion(message=original_message, message_files=[], recipient_agent=recipient_agent)

        try:
            for bot_message in gen:
                if bot_message.sender_name.lower() == "user":
                    continue

                message = bot_message.get_sender_emoji() + " " + bot_message.content

                #############
                # FOR SAVING WORKFLOW
                #############
                if bot_message.sender_name.lower() == "interface manager" and bot_message.receiver_name.lower() == "user":
                    if "Executing Function" not in message:
                        shared_state.workflow_thread_interaction += "\n\n" + f"👤 {bot_message.sender_name} 🗣️ {bot_message.receiver_name}:\n"+ bot_message.content

                #############
                # FOR DISPLAYING CHARTS
                #############
                if "local file path" in message:
                    path = ''
                    paths = re.findall(r'(\S+?\.\w+)', message)
                    for p in paths:
                        possible_path = p.strip()
                        if os.path.exists(possible_path):
                            path = possible_path
                            print('found', path)
                            break
                    print("REGEX PATH FOUND ", path)
                    self.image_path = path

                if self.image_path:
                    sender = bot_message.sender_name.lower()
                    receiver = bot_message.receiver_name.lower()
                    if sender == "graphvisualizer" and receiver == "executing function":
                        message += "\n\nIt has been arranged for the graph to be displayed. You can just tell the Interface Manager that it is AS displayed.."
                        if shared_state.display_all:
                            history.append((None, message))
                        else:
                            shared_state.succinct_backend_workings.append(message)
                            history[-1] = (None, message)

                    elif sender == "visualizationagent" and receiver == "interface manager":
                        message += "\n\nThe graph is as displayed below.."
                        if shared_state.display_all:
                            history.append((None, message))
                            history.append((None, (self.image_path,)))
                        else:
                            shared_state.succinct_backend_workings.append(message)
                            shared_state.succinct_backend_workings.append(self.image_path)
                            history[-1] = (None, message)
                            history[-1] =(None, (self.image_path,))

                    elif sender == "interface manager" and receiver == "user":
                        if not shared_state.display_all:
                            final_message = f"Agent Interactions: {len(shared_state.succinct_backend_workings)} messages"
                            history[-1] = (None,  final_message)
                            shared_state.succinct_backend_workings = []
                        message += "\n\nThe graph is as displayed below.."
                        history.append((None, message))
                        history.append((None, (self.image_path,)))
                        self.image_path = None

                    elif sender == "visualizationagent" and receiver == "workflow manager":
                        message += "\n\nThe graph is as displayed below.."
                        if shared_state.display_all:
                            history.append((None, message))
                            history.append((None, (self.image_path,)))
                        else:
                            shared_state.succinct_backend_workings.append(message)
                            shared_state.succinct_backend_workings.append(self.image_path)
                            history[-1] = (None, message)
                            history[-1] =(None, (self.image_path,))

                    elif sender == "workflow manager" and receiver == "user":
                        if not shared_state.display_all:
                            final_message = f"Agent Interactions: {len(shared_state.succinct_backend_workings)} messages"
                            history[-1] = (None,  final_message)
                            shared_state.succinct_backend_workings = []

                        message += "\n\nThe graph is as displayed below.."
                        history.append((None, message))
                        history.append((None, (self.image_path,)))
                        self.image_path = None

                    else:
                        pass

                else:
                    if shared_state.display_all:
                        # Display everything on Screen
                        history.append((None, message))
                    # else:

                        # if bot_message.sender_name == "User" and "Executing Function" not in message:
                        if shared_state.user_input:
                            placeholder_message = "Processing..."
                            # history.append((None, placeholder_message))
                            # shared_state.user_input = False
                            print(placeholder_message)

                        elif bot_message.sender_name == "Interface Manager" and bot_message.receiver_name == "User" and "Executing Function" not in message:
                            final_message = f"Agent Interactions: {len(shared_state.succinct_backend_workings)} messages"
                            # history[-1] = (None,  final_message)
                            # shared_state.succinct_backend_workings = []
                            # history.append((None, message))
                            print(message)


                        else:
                            high_level_working = ""

                            if bot_message.sender_name == "Interface Manager":
                                high_level_working = f"`{bot_message.sender_name}` is interacting with `{bot_message.receiver_name}`..."

                            if "Interface Manager" in message and "Executing Function" in message:
                                high_level_working = ""

                            if "Workflow Manager" in message and "Executing Function" in message:
                                high_level_working = ""

                            if bot_message.receiver_name == "Interface Manager":
                                high_level_working = f"`{bot_message.sender_name}` has returned back to `{bot_message.receiver_name}` with an update..."

                            if "Interface Manager" not in message and "Executing Function" in message:
                                match = re.search(r"name='(.*?)'", message)
                                if match:
                                    high_level_working = f"`{bot_message.sender_name}` is trying to use the `{match.group(1)}` tool..."

                            if "Workflow Manager" not in message and "Executing Function" in message:
                                match = re.search(r"name='(.*?)'", message)
                                if match:
                                    high_level_working = f"`{bot_message.sender_name}` is trying to use the `{match.group(1)}` tool..."

                            # dealing with tool output
                            if "Function Output" in message:
                                high_level_working = f"The tool `{bot_message.sender_name}` has returned an output..."


                            if high_level_working:
                                shared_state.succinct_backend_workings.append(high_level_working)
                                # history[-1] = (None, high_level_working)
                                print(high_level_working)

                            else:
                                pass

                yield "", history

        except StopIteration:
            pass

    def recipient_agent_completer(self, text, state):
        """
        Autocomplete completer for recipient agent names.
        """
        options = [agent for agent in self.recipient_agents if agent.lower().startswith(text.lower())]
        if state < len(options):
            return options[state]
        else:
            return None

    def setup_autocomplete(self):
        """
        Sets up readline with the completer function.
        """
        self.recipient_agents = [agent.name for agent in self.main_recipients]  # Cache recipient agents for autocomplete
        # readline.set_completer(self.recipient_agent_completer)
        # readline.parse_and_bind('tab: complete')

    def run_demo(self):
        """
        Enhanced run_demo with autocomplete for recipient agent names.
        """
        self.setup_autocomplete()  # Prepare readline for autocomplete

        while True:
            console.rule()
            text = input("👤 USER: ")

            if text.lower() == "exit":
                break

            recipient_agent = None
            if "@" in text:
                recipient_agent = text.split("@")[1].split(" ")[0]
                text = text.replace(f"@{recipient_agent}", "").strip()
                try:
                    recipient_agent = [agent for agent in self.recipient_agents if agent.lower() == recipient_agent.lower()][0]
                    recipient_agent = self.get_agent_by_name(recipient_agent)
                except Exception as e:
                    print(f"Recipient agent {recipient_agent} not found.")
                    continue

            try:
                gen = self.main_thread.get_completion(message=text, recipient_agent=recipient_agent)
                while True:
                    message = next(gen)
                    if message.sender_name.lower() == "user":
                        continue
                    message.cprint()
            except StopIteration as e:
                pass


    def get_customgpt_schema(self, url: str):
        """Returns the OpenAPI schema for the agency from the CEO agent, that you can use to integrate with custom gpts.

        Parameters:
            url (str): Your server url where the api will be hosted.
        """

        return self.ceo.get_openapi_schema(url)

    def plot_agency_chart(self):
        pass

    def _init_agents(self):
        """
        Initializes all agents in the agency with unique IDs, shared instructions, and OpenAI models.

        This method iterates through each agent in the agency, assigns a unique ID, adds shared instructions, and initializes the OpenAI models for each agent.

        There are no input parameters.

        There are no output parameters as this method is used for internal initialization purposes within the Agency class.
        """
        if self.settings_callbacks:
            loaded_settings = self.settings_callbacks["load"]()
            with open(self.settings_path, 'w') as f:
                json.dump(loaded_settings, f, indent=4)

        for agent in self.agents:
            if "temp_id" in agent.id:
                agent.id = None

            agent.add_shared_instructions(self.shared_instructions)
            agent.settings_path = self.settings_path

            if self.shared_files:
                if isinstance(agent.files_folder, str):
                    agent.files_folder = [agent.files_folder]
                    agent.files_folder += self.shared_files
                elif isinstance(agent.files_folder, list):
                    agent.files_folder += self.shared_files

            agent.init_oai()

        if self.settings_callbacks:
            with open(self.agents[0].get_settings_path(), 'r') as f:
                settings = f.read()
            settings = json.loads(settings)
            self.settings_callbacks["save"](settings)

    def _init_threads(self):
        """
        Initializes threads for communication between agents within the agency.

        This method creates Thread objects for each pair of interacting agents as defined in the agents_and_threads attribute of the Agency. Each thread facilitates communication and task execution between an agent and its designated recipient agent.

        No input parameters.

        Output Parameters:
            This method does not return any value but updates the agents_and_threads attribute with initialized Thread objects.
        """
        # load thread ids
        loaded_thread_ids = {}
        if self.threads_callbacks:
            loaded_thread_ids = self.threads_callbacks["load"]()

        for agent_name, threads in self.agents_and_threads.items():
            for other_agent, items in threads.items():
                self.agents_and_threads[agent_name][other_agent] = self.ThreadType(
                    self.get_agent_by_name(items["agent"]),
                    self.get_agent_by_name(
                        items["recipient_agent"]))

                if agent_name in loaded_thread_ids and other_agent in loaded_thread_ids[agent_name]:
                    self.agents_and_threads[agent_name][other_agent].id = loaded_thread_ids[agent_name][other_agent]
                elif self.threads_callbacks:
                    self.agents_and_threads[agent_name][other_agent].init_thread()

        # save thread ids
        if self.threads_callbacks:
            loaded_thread_ids = {}
            for agent_name, threads in self.agents_and_threads.items():
                loaded_thread_ids[agent_name] = {}
                for other_agent, thread in threads.items():
                    loaded_thread_ids[agent_name][other_agent] = thread.id

            self.threads_callbacks["save"](loaded_thread_ids)

    def _parse_agency_chart(self, agency_chart):
        """
        Parses the provided agency chart to initialize and organize agents within the agency.

        Parameters:
            agency_chart: A structure representing the hierarchical organization of agents within the agency.
                    It can contain Agent objects and lists of Agent objects.

        This method iterates through each node in the agency chart. If a node is an Agent, it is set as the CEO if not already assigned.
        If a node is a list, it iterates through the agents in the list, adding them to the agency and establishing communication
        threads between them. It raises an exception if the agency chart is invalid or if multiple CEOs are defined.
        """
        if not isinstance(agency_chart, list):
            raise Exception("Invalid agency chart.")

        if len(agency_chart) == 0:
            raise Exception("Agency chart cannot be empty.")

        for node in agency_chart:
            # handling agents interacting directly with the user
            if isinstance(node, Agent):
                if not self.ceo:
                    self.ceo = node
                    self._add_agent(self.ceo)
                else:
                    self._add_agent(node)
                self._add_main_recipient(node)

            # handling agents interacting with other agents
            elif isinstance(node, list):
                for i, agent in enumerate(node):
                    if not isinstance(agent, Agent):
                        raise Exception("Invalid agency chart.")

                    index = self._add_agent(agent)

                    if i == len(node) - 1:
                        continue
                    
                    if agent.name not in self.agents_and_threads.keys():
                        self.agents_and_threads[agent.name] = {}

                    for other_agent in node:
                        if other_agent.name == agent.name:
                            continue
                        if other_agent.name not in self.agents_and_threads[agent.name].keys():
                            self.agents_and_threads[agent.name][other_agent.name] = {
                                "agent": agent.name,
                                "recipient_agent": other_agent.name,
                            }
            else:
                raise Exception("Invalid agency chart.")

    def _add_agent(self, agent):
        """
        Adds an agent to the agency, assigning a temporary ID if necessary.

        Parameters:
            agent (Agent): The agent to be added to the agency.

        Returns:
            int: The index of the added agent within the agency's agents list.

        This method adds an agent to the agency's list of agents. If the agent does not have an ID, it assigns a temporary unique ID. It checks for uniqueness of the agent's name before addition. The method returns the index of the agent in the agency's agents list, which is used for referencing the agent within the agency.
        """
        if not agent.id:
            # assign temp id
            agent.id = "temp_id_" + str(uuid.uuid4())
        if agent.id not in self.get_agent_ids():
            if agent.name in self.get_agent_names():
                raise Exception("Agent names must be unique.")
            self.agents.append(agent)
            return len(self.agents) - 1
        else:
            return self.get_agent_ids().index(agent.id)

    def _add_main_recipient(self, agent):
        """
        Adds an agent to the agency's list of main recipients.

        Parameters:
            agent (Agent): The agent to be added to the agency's list of main recipients.

        This method adds an agent to the agency's list of main recipients. These are agents that can be directly contacted by the user.
        """
        main_recipient_ids = [agent.id for agent in self.main_recipients]

        if agent.id not in main_recipient_ids:
            self.main_recipients.append(agent)

    def _read_instructions(self, path):
        """
        Reads shared instructions from a specified file and stores them in the agency.

        Parameters:
            path (str): The file path from which to read the shared instructions.

        This method opens the file located at the given path, reads its contents, and stores these contents in the 'shared_instructions' attribute of the agency. This is used to provide common guidelines or instructions to all agents within the agency.
        """
        path = path
        with open(path, 'r') as f:
            self.shared_instructions = f.read()

    def _create_special_tools(self):
        """
        Creates and assigns 'SendMessage' tools to each agent based on the agency's structure.

        This method iterates through the agents and threads in the agency, creating SendMessage tools for each agent. These tools enable agents to send messages to other agents as defined in the agency's structure. The SendMessage tools are tailored to the specific recipient agents that each agent can communicate with.

        No input parameters.

        No output parameters; this method modifies the agents' toolset internally.
        """
        for agent_name, threads in self.agents_and_threads.items():
            recipient_names = list(threads.keys())
            recipient_agents = self.get_agents_by_names(recipient_names)
            agent = self.get_agent_by_name(agent_name)
            agent.add_tool(self._create_send_message_tool(agent, recipient_agents))
            if self.async_mode:
                agent.add_tool(self._create_get_response_tool(agent, recipient_agents))

    def _create_send_message_tool(self, agent: Agent, recipient_agents: List[Agent]):
        """
        Creates a SendMessage tool to enable an agent to send messages to specified recipient agents.


        Parameters:
            agent (Agent): The agent who will be sending messages.
            recipient_agents (List[Agent]): A list of recipient agents who can receive messages.

        Returns:
            SendMessage: A SendMessage tool class that is dynamically created and configured for the given agent and its recipient agents. This tool allows the agent to send messages to the specified recipients, facilitating inter-agent communication within the agency.
        """
        recipient_names = [agent.name for agent in recipient_agents]
        recipients = Enum("recipient", {name: name for name in recipient_names})

        agent_descriptions = ""
        for recipient_agent in recipient_agents:
            if not recipient_agent.description:
                continue
            agent_descriptions += recipient_agent.name + ": "
            agent_descriptions += recipient_agent.description + "\n"

        outer_self = self

        class SendMessage(BaseTool):
            instructions: str = Field(...,
                                      description="Please repeat your instructions step-by-step, including both completed "
                                                  "and the following next steps that you need to perfrom. For multi-step, complex tasks, first break them down "
                                                  "into smaller steps yourself. Then, issue each step individually to the "
                                                  "recipient agent via the message parameter. Each identified step should be "
                                                  "sent in separate message. Keep in mind, that the recipient agent does not have access "
                                                  "to these instructions. You must include recipient agent-specific instructions "
                                                  "in the message parameter.")
            recipient: recipients = Field(..., description=agent_descriptions)
            message: str = Field(...,
                                 description="Specify the task required for the recipient agent to complete. Focus on clarifying what the task entails, rather than providing exact instructions. Most importantly, mention the type of memories that have been updated for the current task at hand. Telling the recipient agent about the what types of memories have been updated is very very important and should be included here.")
            message_files: List[str] = Field(default=None,
                                             description="A list of file ids to be sent as attachments to this message. Only use this if you have the file id that starts with 'file-'.",
                                             examples=["file-1234", "file-5678"])

            @field_validator('recipient')
            def check_recipient(cls, value):
                if value.value not in recipient_names:
                    raise ValueError(f"Recipient {value} is not valid. Valid recipients are: {recipient_names}")
                return value

            def run(self):
                thread = outer_self.agents_and_threads[self.caller_agent.name][self.recipient.value]

                if not outer_self.async_mode:
                    gen = thread.get_completion(message=self.message, message_files=self.message_files)
                    try:
                        while True:
                            yield next(gen)
                    except StopIteration as e:
                        message = e.value
                else:
                    message = thread.get_completion_async(message=self.message, message_files=self.message_files)

                return message or ""

        SendMessage.caller_agent = agent
        if self.async_mode:
            SendMessage.__doc__ = self.send_message_tool_description_async
        else:
            SendMessage.__doc__ = self.send_message_tool_description

        return SendMessage

    def _create_get_response_tool(self, agent: Agent, recipient_agents: List[Agent]):
        """
        Creates a CheckStatus tool to enable an agent to check the status of a task with a specified recipient agent.
        """
        recipient_names = [agent.name for agent in recipient_agents]
        recipients = Enum("recipient", {name: name for name in recipient_names})

        outer_self = self

        class GetResponse(BaseTool):
            """This tool allows you to check the status of a task or get a response from a specified recipient agent, if the task has been completed. You must always use 'SendMessage' tool with the designated agent first."""
            recipient: recipients = Field(...,
                                          description=f"Recipient agent that you want to check the status of. Valid recipients are: {recipient_names}")
                                          

            @field_validator('recipient')
            def check_recipient(cls, value):
                if value.value not in recipient_names:
                    raise ValueError(f"Recipient {value} is not valid. Valid recipients are: {recipient_names}")
                return value

            def run(self):
                thread = outer_self.agents_and_threads[self.caller_agent.name][self.recipient.value]

                return thread.check_status()

        GetResponse.caller_agent = agent

        return GetResponse

    def get_agent_by_name(self, agent_name):
        """
        Retrieves an agent from the agency based on the agent's name.

        Parameters:
            agent_name (str): The name of the agent to be retrieved.

        Returns:
            Agent: The agent object with the specified name.

        Raises:
            Exception: If no agent with the given name is found Fin the agency.
        """
        for agent in self.agents:
            if agent.name == agent_name:
                return agent
        raise Exception(f"Agent {agent_name} not found.")

    def get_agents_by_names(self, agent_names):
        """
        Retrieves a list of agent objects based on their names.

        Parameters:
            agent_names: A list of strings representing the names of the agents to be retrieved.

        Returns:
            A list of Agent objects corresponding to the given names.
        """
        return [self.get_agent_by_name(agent_name) for agent_name in agent_names]

    def get_agent_ids(self):
        """
        Retrieves the IDs of all agents currently in the agency.

        Returns:
            List[str]: A list containing the unique IDs of all agents.
        """
        return [agent.id for agent in self.agents]

    def get_agent_names(self):
        """
        Retrieves the names of all agents in the agency.

        Returns:
            List[str]: A list of names of all agents currently part of the agency.
        """
        return [agent.name for agent in self.agents]

    def get_recipient_names(self):
        """
        Retrieves the names of all agents in the agency.

        Returns:
            A list of strings, where each string is the name of an agent in the agency.
        """
        return [agent.name for agent in self.agents]

    def get_class_folder_path(self):
        """
        Retrieves the absolute path of the directory containing the class file.

        Returns:
            str: The absolute path of the directory where the class file is located.
        """
        return os.path.abspath(os.path.dirname(inspect.getfile(self.__class__)))
