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
        # if len(self.messages) >= 2 and self.messages[-2]['role'] == 'user':
        #     message_content = self.messages[-2]['content']
        #     successful_list_files_re = re.compile('list_files.*files found')
        #     if successful_list_files_re.search(message_content) and (not self.last_list_files_result or len(self.last_list_files_result) > len(message_content)):
        #         self.last_list_files_result = message_content
        #         self.messages[-2]['content'] = "last successful result of list_files: {}".format(message_content)
        #         for old_message in self.messages[:-2]:
        #             list_files_re = re.compile('list_files')
        #             if list_files_re.search(old_message['content']) and old_message['role'] == 'user':
        #                 old_message['content'] = 'check the next message to see what you thought about this message'
        self.messages.append({"role": "user", "content": message})
        result = self.execute()
        # memory optimization for readfile (split out later)
        successful_read_file_re = re.compile('lines [0-9]+-[0-9]+')
        read_file_match = successful_read_file_re.search(result)
        if read_file_match:
            relevant_lines = read_file_match.group().replace("lines ", "").split('-')
            stripped_message = re.sub(r"result of -- running read_file.*]:", "", message.strip()).strip()
            file_lines = ast.literal_eval(stripped_message)
            relevant_file_lines = file_lines[(int(relevant_lines[0]) - 1):(int(relevant_lines[1]) - 1)]
            new_message = "relevant lines found after running read_file with [\'/frontend/index.js\']: {}".format(relevant_file_lines)
            self.messages[-1]['content'] = new_message

        self.messages.append({"role": "assistant", "content": result})
        for message in self.messages[1:]:
            print("message: {}".format(message), end='\n\n')
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
Use Thought to describe your thoughts about the coding task, results of actions you have taken,
or why you plan to take the action you plan to take next.
Use Action to run one of the actions available to you - then return PAUSE.
Wait for the developer to respond to your message before continuing.
At the end of a loop cycle you either take the result of the last action as input to generate
your next action, or you stop looping if you think the coding task is complete

Your available actions are:

list_files:
Given a starting directory as an argument, lists files in a directory tree (max depth 2)
Use the initial coding task and any previous action results to call this action with a starting file directory.
Use the result of this action to figure out which file to look at or if you need to first list files with a different starting directory.
If you don't know which starting directory to start in, start with '/'.

read_file:
Given a filename as an argument, reads the file and returns the lines of the file as a list, either all the lines or just the relevant lines.
Use the result of this action to figure out which line(s) of code to change or if you to need first look in another file.
If you can't find the code that needs to change, you most likely need to look in another file first.
If you do find relevant code make sure to say which lines of code are relevant in your Thought.
When mentioning relevant lines you need to use the syntax "line [beginning line number]-[ending line number]".
It can also be helpful to mention any relevant functions or methods and summarize what they do.

change_file:
Given a file path and a dictionary of proposed changes, update the file with your proposed changes.
The dictionary of changes needs to have line numbers as keys with values being a touple with the first touple
entry being "add", "replace", or "delete", and the second touple entry being the change to make (an empty string in the case of deletion).

Example session 1:

Coding Task: We have a game of Tetris I'd like to prevent users from scrolling up and down in the browser when pressing the up and down arrow keys respectively

Thought: I should find the file where arrow keyboard events are handled.
Action: list_files, Arg: /
PAUSE

(Developer responds with a list of files in the root directory)

Thought: I see that the root directory is the correct starting directory. Let me look at the /frontend/index.js file to see if that's where the arrow keyboard events are handled.
Action: read_file, Arg: /frontend/index.js
PAUSE

(Developer responds with the contents of the /frontend/index.js file)

Thought: Looks like the relevant code is from lines 61-71 in /frontend/index.js in the handleKeyDown function. The handleKeyDown function
         translates keyboard events into tetris piece movements and then calls the movePiece function with one of those piece movements. 
         I should prevent the default behavior of keyboard events before any of that logic is called.
Action: change_file, Arg: /frontend/index.js, Arg: {61: ('add', '    e.preventDefault()\n')}
PAUSE

(Developer either tells you that the changes were made or that the changes were not made and why)


Example session 2:

Coding Task: We have multiple registration endpoints that our users can use to register for our service. There's duplicative logic in each.
             We should move the duplicative logic into the RegistrationController.py file and then call that logic from each endpoint.

Thought: I should first find the file where the registration endpoints are defined.
Action: list_files, Arg: /
PAUSE

(Developer responds with a list of files in the root directory)

Thought: I see that the root directory is the correct starting directory. Let me look at the /app/routes directory.
Action: list_files, Arg: /app/routes
PAUSE

(Developer responds with a list of files in the /app/routes directory)

Thought: The /app/routes/__init__.py file looks promising. Let me look at that file.
Action: read_file, Arg: /app/routes/__init__.py
PAUSE

(Developer responds with the contents of the /app/routes/__init__.py file)

Thought: Looks like the relevant code is from lines 51-76 and lines 94-112 in /app/routes/__init__.py. There, we see a '/user/register' endpoint, 
         and a '/user/freemium/register' endpoint. Both call the validateEmail() and validatePassword() functions. I should move those functions
         to the RegistrationController.py file and then call them from each endpoint. Let's first checkout the RegistrationController.py file.
Action: list_files, Arg: /app/controllers
PAUSE

(Developer responds with a list of files in the /app/controllers directory)

Thought: I found RegistrationController.py. Let me look at that file.
Action: read_file, Arg: /app/controllers/RegistrationController.py
PAUSE

(Developer responds with the contents of the /app/controllers/RegistrationController.py file)

Thought: I didn't see any code that would necessarily be a good place to put the duplicative code from the register endpoints.
         So, I'd suggest creating a new method under the RegistrationController class called validateEmailAndPassword().
Action: change_file, Arg: /app/controllers/RegistrationController.py, Arg: {1: ('add', 'import (validateEmail, validatePassword from './ValidationController.py \n'), 10: ('add', '  def validateEmailAndPassword(email, password):\n'), 11: ('add', '    validateEmail(email)\n'), 12: ('add', '    validatePassword(password)\n')}
PAUSE

(Developer either tells you that the changes were made or that the changes were not made and why)

Thought: Now that I've created the validateEmailAndPassword() method, I should call it from the '/user/register' and '/user/freemium/register' endpoints.
Action change_file: Arg: /app/routes/__init__.py, Arg: {1: ('add', 'import (validateEmailAndPassword from '../controllers/RegistrationController.py \n'), 53: ('replace', '  validateEmailAndPssword(email, password)\n'), 54: ('delete', ''), 95: ('replace', '  validateEmailAndPssword(email, password)\n'), 96: ('delete', '')}

(Developer either tells you that the changes were made or that the changes were not made and why)

Continue iterating like this until you make the necessary changes to complete the coding task.
""".strip()


action_re = re.compile('^Action: (.*)$')


def coding_task(task, max_turns=8):
    i = 0
    bot = ChatBot(prompt)
    next_prompt = "Coding Task: {}".format(task)
    while i < max_turns:
        i += 1
        result = bot(next_prompt)
        print(result)
        actions = [action_re.match(a) for a in result.split('\n') if action_re.match(a)]
        if actions:
            # There is an action to run
            action_list = actions[0].string.split(', Arg: ')
            action = action_list[0].split('Action: ')[1]
            action_args = action_list[1:]
            if action not in known_actions:
                raise Exception("Unknown action: {}: {}".format(action, action_args))
            print(" -- running {} {}".format(action, action_args))
            action_result = known_actions[action](*action_args)
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
        MAX_DEPTH = 2
        depth = 0
        for dir_entry in os.scandir(".{}".format(starting_dir)):
            if dir_entry.is_file():
                file_paths.append(dir_entry.path)
            elif dir_entry.is_dir() and ('.git' not in dir_entry.path):
                depth += 1
                if depth <= MAX_DEPTH:
                    sub_file_paths = helper(starting_dir=dir_entry.path[1:])
                    file_paths = file_paths + sub_file_paths
                else:
                    file_paths.append(dir_entry.path)
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
                new_file_lines = new_file_lines[:line_num] + ["{}\n".format(change[1])] + old_file_lines[line_num - line_num_differential:]
            if change[0] == 'delete':
                new_file_lines = new_file_lines[:line_num] + old_file_lines[line_num - line_num_differential:]
                line_num_differential -= 1
        with open(".{}".format(filepath), 'w') as file:
            file.writelines(new_file_lines)
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
