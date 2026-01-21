import os
from dotenv import load_dotenv

# Get langchain dependencies
from langchain.agents import create_agent
from langchain_google_genai import ChatGoogleGenerativeAI

from get_resume import get_resume
from url_loader import get_linkedin_job

load_dotenv()

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")


def initialize_agent():
    model = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0)

    agent = create_agent(
        model=model,
        tools=[],
        system_prompt="""You are a helpful job matcher that can match a job description to a resume. 
        You will be given a job description and a resume. 
        You will try to find how closely the candidate with the resume closely to the job description.
        Please categorize the closeness of the match into a scale of 1 to 10. 10 is the most relevant.
        Please point out the key skills, experiences, and accomplishments that are most relevant to the job description.
        Please point out the key skills, experiences, and accomplishments that are not relevant to the job description.
        Please point out the key skills, experiences, and accomplishments that are not relevant to the job description.
        Please present the results in a structured format and brief.""")

    resume = get_resume("resume.txt")

    job_description = get_linkedin_job("https://www.linkedin.com/jobs/view/4358994928/")
    user_message = "resume: " + resume + "\njob description: " + job_description
        
    results = agent.invoke({"messages": [{"role": "user", "content": user_message}]})
    for message in results.get("messages"):
        print(message.content)


def main():
    initialize_agent()

if __name__ == "__main__":
    main()


