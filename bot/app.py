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
        completion = openai.ChatCompletion.create(model="gpt-3.5-turbo", messages=self.messages)
        # Uncomment this to print out token usage each time, e.g.
        # {"completion_tokens": 86, "prompt_tokens": 26, "total_tokens": 112}
        print(completion.usage)
        return completion.choices[0].message.content


prompt = """
You run in a loop of Thought, Action, PAUSE, Observation.
At the end of the loop you output an Answer
Use Thought to describe your thoughts about the question you have been asked.
Use Action to run one of the actions available to you - then return PAUSE.
Observation will be the result of running those actions.

Your available actions are:

find_file:
e.g. task: figure out why my code isn't working, starting directory: /main
Given a coding task and a starting file directory, figure out which file to look at.

read_file:
e.g. task: figure out why my code isn't working, file: /main/app.py, user feedback (option): that's not exactly right
Given a coding task, optional user feedback and a file to work in, read the file and output thoughts about needed change

change_file:
e.g. proposed change: update line 14 to have the correct syntax, file: /main/app.py
Given a file path and a dictionary of file lines and corresponding proposed changes, update the file with your proposed changes

Your goal is to iterate through these actions with the help of a developer until the original coding task is achieved

Example session:

Coding Task: We have a built game of Tetris. The arrow keys are used to move pieces, but pressing up also scrolls the
             user up and down in the browser. Prevent this from happening.
Thought: I should find the file where arrow keyboard events are handled.
Actions: find_file and read_file
PAUSE

You then output where you think the relevant code is:

Observation: I think the relevant code is in eventHandlers.js lines 14-17.

If you're certain that's where the relevant code is precede with a change_file action. If not ask the developer if you are
correct.

Once you've ran a change_file action summarize your changes and/or show the diff.
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
        if actions:
            # There is an action to run
            action, action_input = actions[0].groups()
            if action not in known_actions:
                raise Exception("Unknown action: {}: {}".format(action, action_input))
            print(" -- running {} {}".format(action, action_input))
            observation = known_actions[action](action_input)
            print("Observation:", observation)
            next_prompt = "Observation: {}".format(observation)
        else:
            return


def find_file(starting_dir=''):
    file_paths = []
    # not sure if this is really an issue, hopefully hardcoding the beginning of the starting path will prevent the AI
    # from being able to search the whole computer
    for dir_entry in os.scandir("./{}".format(starting_dir)):
        if dir_entry.is_file():
            file_paths.append(dir_entry.path)
        elif dir_entry.is_dir():
            sub_file_paths = find_file(starting_dir=dir_entry.path[2:])
            file_paths = file_paths + sub_file_paths
    return file_paths


def read_file(filepath):
    file_lines = []
    num = 1
    with open("./{}".format(filepath)) as file:
        for line in file:
            file_lines.append(line)
            num += 1
    return file_lines


def change_file(filepath, changes):
    file_lines = open("./{}".format(filepath)).readlines()
    for line, change in changes:
        file_lines[line] = change
    with open("./{}".format(filepath), 'w') as file:
        file.writelines(file_lines)


known_actions = {
    "find_file": find_file,
    "read_file": read_file,
    "change_file": change_file
}


def __main__():
    print('What code task can I help you with today?')
    task = input()
    coding_task(task)


__main__()
