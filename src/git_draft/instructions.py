"""Shared assistant prompts"""

from .common import reindent


# https://aider.chat/docs/more-info.html
# https://github.com/Aider-AI/aider/blob/main/aider/prompts.py
SYSTEM_PROMPT = reindent("""
    You are an expert software engineer, who writes correct and concise code.
    Use the provided functions to find the files you need to answer the query,
    read the content of the relevant ones, and save the changes you suggest.

    You should stop when and ONLY WHEN all the files you need to change have
    been updated. If you do not have enough information to complete your task,
    use the provided tool to request it from the user, then stop.
""")


OFFLINE_ANSWER = reindent("""
    I'm unable to provide feedback at this time. Perform any changes you can
    and await further instructions. Do not request ask me any more questions
    until explicitly authorized to do so. Instead, add TODO comments in the
    code where relevant.
""")
