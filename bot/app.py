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
        self.last_list_files_result = None
        if self.system:
            self.messages.append({"role": "system", "content": system})

    def __call__(self, message):
        # memory summarization: keep the action result if it was the last successful list_files action otherwise
        # replace it with a message saying to check the next message to see what you thought about this message
        if len(self.messages) >= 2 and self.messages[-2]['role'] == 'user':
            message_content = self.messages[-2]['content']
            successful_list_files_re = re.compile('list_files.*files found')
            if successful_list_files_re.search(message_content) and (not self.last_list_files_result or len(self.last_list_files_result) > len(message_content)):
                self.last_list_files_result = message_content
                self.messages[-2]['content'] = "last successful result of list_files: {}".format(message_content)
                for old_message in self.messages[:-2]:
                    list_files_re = re.compile('list_files')
                    if list_files_re.search(old_message['content']) and old_message['role'] == 'user':
                        old_message['content'] = 'check the next message to see what you thought about this message'
            else:
                self.messages[-2]['content'] = 'check the next message to see what you thought about this message'
        self.messages.append({"role": "user", "content": message})
        # print(self.messages)
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
Use the initial coding task and any previous list_files action results to call this action with a file path.
Use the result of this action to figure out which line(s) of code to change or if you to need first look in another file.

change_file:
e.g. task: figure out why my code isn't working, file: /main/app.py
Given a file path and a dictionary of file lines and corresponding proposed changes, update the file with your proposed changes

Your goal is to iterate through these actions until the original coding task is achieved

Example session:

Coding Task: We have a built game of Tetris. The arrow keys are used to move pieces, but pressing up also scrolls the
             user up and down in the browser. Prevent this from happening.
Thought: I should find the file where arrow keyboard events are handled.
Action: list_files: /
PAUSE

Thought: Given the results of list_files: /, I should look in the /frontend/eventHandlers.js file.
Action: read_file: /frontend/eventHandlers.js
PAUSE

Continue iterating like this until you make the necessary changes to complete the coding task.
""".strip()


action_re = re.compile('^Action: (\w+): (.*)$')


def coding_task(task, max_turns=8):
    i = 0
    bot = ChatBot(prompt)
    next_prompt = task
    while i < max_turns:
        i += 1
        result = bot(next_prompt)
        print(result)
        actions = [action_re.match(a) for a in result.split('\n') if action_re.match(a)]
        # print("actions: {}".format(actions))
        if actions:
            # There is an action to run
            action, action_input = actions[0].groups()
            if action not in known_actions:
                raise Exception("Unknown action: {}: {}".format(action, action_input))
            print(" -- running {} {}".format(action, action_input))
            action_result = known_actions[action](action_input)
            # print("Action Result:", action_result)
            next_prompt = "result of -- running {} {}: {}".format(action, action_input, action_result)
        else:
            return


def list_files(starting_dir=''):
    preface = 'files found: '
    try:
        os.scandir(".{}".format(starting_dir))
    except FileNotFoundError:
        starting_dir = ''
        preface = "That starting file directory doesn't exist. Here's a list of files starting at the root directory: "

    def helper(starting_dir):
        file_paths = []
        for dir_entry in os.scandir(".{}".format(starting_dir)):
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
    truncated_file_path = filepath if filepath[0] == '/' else filepath[1:]
    try:
        with open(".{}".format(truncated_file_path)) as file:
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
