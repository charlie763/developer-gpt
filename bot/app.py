# stealing heavily from https://til.simonwillison.net/llms/python-react-pattern

import os
import openai
import re
import ast
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
        result = self.execute()
        self.messages.append({"role": "assistant", "content": result})
        # print(self.messages)
        return result

    def execute(self):
        completion = openai.ChatCompletion.create(model="gpt-3.5-turbo", messages=self.messages, temperature=0.1)
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
If you can't find the code that needs to change, you most likely need to look in another file first.

change_file:
e.g. task: figure out why my code isn't working, file: /main/app.py
Given a file path and a dictionary of proposed changes, update the file with your proposed changes.
The dictionary of changes needs to have line numbers as keys with values being a touple with the first touple
entry being "add", "replace", or "delete", and the second touple entry being the change to make (an empty string in the case of deletion).

Your goal is to iterate through these actions until the original coding task is achieved

Example session:

Coding Task: We have a built game of Tetris. The arrow keys are used to move pieces, but pressing up also scrolls the
             user up and down in the browser. Prevent this from happening.
Thought: I should find the file where arrow keyboard events are handled.
Action: list_files, Arg: /
PAUSE

Thought: Given the results of list_files: /, I should look in the /frontend/eventHandlers.js file.
Action: read_file, Arg: /frontend/eventHandlers.js
PAUSE

Thought: I can't find the relevant code in /frontend/eventHandlers.js. I should look in another file. Let me look at other list_files results.
Action: read_file, Arg: /frontend/index.js
PAUSE

Thought: Looks like the relevant code is from line 14-17 in /frontend/index.js. I should change the code on those lines.
Action: change_file, Arg: /frontend/index.js, Arg: {15: ('add', '    e.preventDefault()')}
PAUSE

Continue iterating like this until you make the necessary changes to complete the coding task.
""".strip()


action_re = re.compile('^Action: (.*)$')


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
            action_list = actions[0].string.split(', Arg: ')
            # action, action_input = actions[0].groups()
            action = action_list[0].split('Action: ')[1]
            action_args = action_list[1:]
            # print("action_input: {}".format(action_args))
            if action not in known_actions:
                raise Exception("Unknown action: {}: {}".format(action, action_args))
            print(" -- running {} {}".format(action, action_args))
            action_result = known_actions[action](*action_args)
            # print("Action Result:", action_result)
            next_prompt = "result of -- running {} {}: {}".format(action, action_args, action_result)
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
    # try doing changes as list of touples [(line num, add/replace/delete, change)]
    # keep old version of file until complete and keep a line number differential for the new file being constructed
    print('Do you want to make the following changes to {}: {}?'.format(filepath, changes))
    print('(reply "yes" if you want to continue with the file change, or given an explanation of why not for the ai if not)')
    user_input = input()
    if user_input == 'yes':
        changes_dict = ast.literal_eval(changes)
        old_file_lines = open("./{}".format(filepath)).readlines()
        new_file_lines = [*old_file_lines]
        line_num_differential = 0
        for line_num, change in changes_dict.items():
            if change[0] == 'add':
                new_file_lines = new_file_lines[:line_num] + ["{}\n".format(change[1])] + old_file_lines[line_num - line_num_differential:]
                line_num_differential += 1
            if change[0] == 'replace':
                new_file_lines = new_file_lines[:line_num + line_num_differential - 1] + ["{}\n".format(change[1])] + old_file_lines[line_num:]
            if change[0] == 'delete':
                new_file_lines = new_file_lines[:line_num + line_num_differential - 1] + old_file_lines[line_num:]
                line_num_differential -= 1
        return "The File changed successfully"
    else:
        return "The File was not changed because: {}".format(user_input)


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
