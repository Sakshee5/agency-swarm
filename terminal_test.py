from agency_swarm.agency.research_and_sensing import ResearchSensingAgency
from agency_swarm.agency.human_capital import HumanCapitalAgency

# instantiate required agency
agency = ResearchSensingAgency()


# start the conversation
history = None      # default state
workflow = False    # True to use existing workflow, False to start a new one
while True:
    ori_message = input("Enter your message: ")      # python input() function to get user input
    history = agency.user_input(ori_message, history, workflow)
    bot_messages = agency.bot_output(ori_message, history, workflow)
    try:
        for message, history in bot_messages:
            print(message)
            print("\n")
            if history[-1][0]:
                print(history[-1][0])
            else:
                print(history[-1][1])
    except StopIteration:
        continue
