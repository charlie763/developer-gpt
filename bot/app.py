# stealing heavily from https://til.simonwillison.net/llms/python-react-pattern

import os
import openai
import re
from decouple import config


openai.api_key = config("OPENAI_API_KEY")


class ChatBot:
    def __init__(self, system=""):
        self.system = system
        self.messages = []
        if self.system:
            self.messages.append({"role": "system", "content": system})

    def __call__(self, message):
        self.messages.append({"role": "user", "content": message})
        result = self.execute()
        self.messages.append({"role": "assistant", "content": result})
        return result

    def execute(self):
        completion = openai.ChatCompletion.create(model="gpt-3.5-turbo", messages=self.messages, temperature=0)
        # Uncomment this to print out token usage each time, e.g.
        # {"completion_tokens": 86, "prompt_tokens": 26, "total_tokens": 112}
        print(completion.usage)
        return completion.choices[0].message.content


prompt = """
Your goal is to help a developer achieve a coding task.
You run in a loop of Thought, Action, PAUSE.
Use Thought to describe your thoughts about the question you have been asked.
Use Action to run one of the actions available to you - then return PAUSE.
At the end of a loop cycle you either take the result of the last action as input to generate
your next action, or you stop looping if you think the coding task is complete

Your available actions are:

list_files:
e.g. task: figure out why my code isn't working, starting directory: /main
Use the initial coding task and any previous action results to call this action with a starting file directory.
Use the result of this action to figure out which file to look at or if you need to first list files with a different starting directory.

read_file:
e.g. task: figure out why my code isn't working, file: /main/app.py
Use the initial coding task and any previous action results to call this action with a file path.
Use the result of this action to figure out which line(s) of code to change or if you need first look in another file.

change_file:
e.g. task: figure out why my code isn't working, file: /main/app.py
Given a file path and a dictionary of file lines and corresponding proposed changes, update the file with your proposed changes

Your goal is to iterate through these actions with the help of a developer until the original coding task is achieved

Example session:

Coding Task: We have a built game of Tetris. The arrow keys are used to move pieces, but pressing up also scrolls the
             user up and down in the browser. Prevent this from happening.
Thought: I should find the file where arrow keyboard events are handled.
Action: list_files: /lib
PAUSE

Thought: Given the results of list_files: /lib, I should look in the /frontend/eventHandlers.js file.
Action: read_file: /frontend/eventHandlers.js 
PAUSE

Continue iterating like this until you make the necessary changes to complete the coding task.
""".strip()


action_re = re.compile('^Action: (\w+): (.*)$')


def coding_task(task, max_turns=5):
    i = 0
    bot = ChatBot(prompt)
    next_prompt = task
    while i < max_turns:
        i += 1
        result = bot(next_prompt)
        print(result)
        actions = [action_re.match(a) for a in result.split('\n') if action_re.match(a)]
        print("actions: {}".format(actions))
        if actions:
            # There is an action to run
            action, action_input = actions[0].groups()
            if action not in known_actions:
                raise Exception("Unknown action: {}: {}".format(action, action_input))
            print(" -- running {} {}".format(action, action_input))
            action_result = known_actions[action](action_input)
            print("Action Result:", action_result)
            next_prompt = "result of -- running {} {}: {}".format(action, action_input, action_result)
        else:
            return


def list_files(starting_dir=''):
    preface = 'files found: '
    try: 
        os.scandir(".{}".format(starting_dir))
    except FileNotFoundError:
        starting_dir=''
        preface = "That starting file directory doesn't exist. Here's a list of files starting at the root directory: "
    # not sure if this is really an issue, hopefully hardcoding the beginning of the starting path will prevent the AI
    # from being able to search the whole computer
    def helper(starting_dir):
        file_paths = []
        for dir_entry in os.scandir(".{}".format(starting_dir)):
        # for dir_entry in os.scandir():
            if dir_entry.is_file():
                file_paths.append(dir_entry.path)
            elif dir_entry.is_dir():
                sub_file_paths = helper(starting_dir=dir_entry.path[1:])
                file_paths = file_paths + sub_file_paths
        return file_paths
    return "{}{}".format(preface, helper(starting_dir))


def read_file(filepath):
    file_lines = []
    num = 1
    # use len to keep track of each line and then keep a total count of char/tokens 4:1 ratio
    # then stop if, too much
    try:
        with open(".{}".format(filepath[1:])) as file:
            for line in file:
                file_lines.append("{}. {}".format(num, line))
                num += 1
        return file_lines
    except FileNotFoundError:
        return "That file doesn't exist. Try again. Only try files resulting from a list_files action."


def change_file(filepath, changes):
    file_lines = open("./{}".format(filepath)).readlines()
    for line, change in changes.items():
        file_lines[line] = change
    with open("./{}".format(filepath), 'w') as file:
        file.writelines(file_lines)


known_actions = {
    "list_files": list_files,
    "read_file": read_file,
    "change_file": change_file
}


def __main__():
    print('What code task can I help you with today?')
    task = input()
    coding_task(task)


__main__()
