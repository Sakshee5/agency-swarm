from agency_swarm import Agent
from agency_swarm.tools.research_and_sensing import ClassifyText, ClassifyExcelEntries
from agency_swarm.tools.all_purpose_tools.FileManagement import UpdateWorkingMemory, UpdateWorkingLongtermMemory


class ClassificationAgent(Agent):

    def __init__(self, **kwargs):
        # Initialize tools in kwargs if not present
        if 'tools' not in kwargs:
            kwargs['tools'] = []

        # Add required tools
        kwargs['tools'].extend([ClassifyText, ClassifyExcelEntries])

        if 'description' not in kwargs:
            kwargs['description'] = "Handles classification related queries. Either needs input as raw text to classify or an excel file input with multiple entries to classify. Capable of single and multi-level classification. Can also handle classification of multiple taxonomies at once. Needs the names of the taxonomy files and corresponding column names for each level."

        # Set instructions
        if 'instructions' not in kwargs:
            kwargs['instructions'] = "./instructions.md"

        # Initialize the parent class
        super().__init__(**kwargs)
