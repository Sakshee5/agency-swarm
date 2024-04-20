from pydantic import Field
from agency_swarm import BaseTool
from agency_swarm.util import get_openai_client
import json
from typing import List
from openai import AzureOpenAI
from agency_swarm.agents.research_and_sensing.SummarizationAgent import SummarizationAgent
from agency_swarm.agents.research_and_sensing.ClassificationAgent import ClassificationAgent
from agency_swarm.agents.research_and_sensing.DataSourcingAgent import DataSourcingAgent
from agency_swarm.agents.research_and_sensing.TopicModelingAgent import TopicModelingAgent
from agency_swarm.agents.research_and_sensing.QandAAgent import QandAAgent
from agency_swarm.agents.research_and_sensing.VisualizationAgent import VisualizationAgent


class WorkflowPlanning(BaseTool):
    """
    This tool is used to plan a workflow behoredhand for reference, if the user query seems indirect or complicated. It helps in how the available agents can be used to fulfill the user query. Ensure to provide all details in the query to get a detailed plan.
    """
    detailed_query: str = Field(..., description="The query to be used for workflow planning. Should contain all details and clarifications, of what the user is expecting to come up with a relevant plan. If user is requesting for any changes or checkpoints to the plan, mention them here as well!")

    def run(self):
        available_agents_with_decsription = f"""DataSourcingAgent:
{DataSourcingAgent().description}

SummarizationAgent:
Handles summarization related queries. Capable of receiving input as a single raw text to summarize or multiple entries from an excel file to summarize.

ClassificationAgent:
{ClassificationAgent().description}

TopicModelingAgent:
{TopicModelingAgent().description}

QandAAgent:
{QandAAgent().description}

VisualizationAgent:
{VisualizationAgent().description}"""
        sys_message = """Your task is to plan a workflow based on the query provided by the user by carefully analyzing the descriptions of agents that you can delegate tasks to. Your job here is to explore all possible options i.e., all the possible ways you can chain the provided agents to fulfill the user query. You need to provide a detailed plan of how you will chain the agents together to fulfill the user query."""

        user_message = f"""You can use the descriptions of the agents provided below to understand the capabilities of each agent and how they can be used to fulfill the user query. If any user clarification is required, you can also mention them with the question so that they can be asked to the user.

Capabilties of available agents:
{available_agents_with_decsription}

Query:
{self.detailed_query}

As final output, return something as the follows. It should be succinct and to the point. Don't include any unnecessary details.

1. First use `xyz` agent to do `abc` task.

2. If the output of `xyz` agent is `pqr`, then use `lmn` agent to do `opq` task. 
`User Clarificaiton`: `lmn` agent will require this parameter to do the task. Only mention parameters that the user needs to be defined. User shouldnt be bothered with parameters that will com from the output of previous agent.

3. If the output of `xyz` agent is `lmn`, you can explore `def` agent to do `rst` task. 
`User Clarificaiton`: ...

Basically, you need to provide a detailed plan of how you will chain the agents together to fulfill the user query and also try to reason out the choices you make with possible outcomes and ways to deal with them. If something is not possible, you can mention that as well and say maybe it would've worked if such and such a thing was possible.
"""


        messages = [{'role': 'system', 'content': sys_message},
                    {'role': 'user', 'content': user_message}]
        

        client = AzureOpenAI()
        response = client.chat.completions.create(
                    model="gpt4",
                    messages=messages,
                    temperature=0,
                )

        plan = response.choices[0].message.content

        return "Reference Plan: \n" + plan
