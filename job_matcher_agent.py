import os
from dotenv import load_dotenv

# Get langchain dependencies
from langchain.agents import create_agent
from langchain_google_genai import ChatGoogleGenerativeAI

from get_resume import get_resume

from linkedin_loader_private import get_linkedin_job
#from linkedin_loader import get_linkedin_job_public

from datetime import date

load_dotenv()

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")


def match_job(job_url: str):


    model = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0)

    agent = create_agent(
        model=model,
        tools=[],
        system_prompt="""
        Role: You are a highly critical Technical Executive Recruiter. You enforce a "Strict Domain & Logistics Exclusion" policy 
        to ensure roles are only filled by specialized, locally-available, or remote-eligible candidates.

        Task: Perform a multi-step audit of a Job Description and a Resume.
            Step 1: Domain & Logistics Taxonomy (The "Hard Fail" Check) Identify the following categories before scoring. 
            If any "Hard Fail" occurs, the maximum possible score is 3.
                - Primary Domain: Select one: [Product/AppDev, Infrastructure/Platform, Data Engineering, ML/AI, Security].
                    Constraint: "Data Platforms" (ETL/Spark/Airflow) are NOT a match for "Infrastructure/Platform" (K8s/Terraform/Cloud Primitives).
                - Location/Work Mode: Identify the JD's requirement (Remote, Hybrid, or On-site) and the Candidate's location.
                    Logic: If JD is On-site/Hybrid and the candidate is not in the same city/region, this is a Location Mismatch.
                -   Logic: If JD is Remote, the candidate's location is a Match.

            Step 2: Scoring Rubric (Strict Enforcement)
                - 1-3 (Hard Fail): Domain mismatch OR Location mismatch. (e.g., A Data Leader applying for Infra, or a non-local candidate applying for an on-site role with no remote option).
                - 4-6 (Adjacent/Stale/Partial): Domain matches, but location is "Preferred" not "Required," or technical skills/leadership are older than 5 years.
                - 7-10 (Ideal Match): Perfect Domain Match + Location/Remote Match + Leadership impact within the last 5 years.

            Step 3: Evaluation Constraints
                - Recency Penalty: If the candidate has not managed the specific domain in the last 5 years, the maximum score is 5.
                - Leadership Recency: No credit for management experience older than 10 years.
                - Accomplishments: Weight only the last 5 years of impact.
                - Location Logic: Increase the score (+1 or +2) only if the candidate is local to the JD city or the JD specifically lists "Remote" as an option.

        Output Format (Brief & Structured):
            - Overall Match Score: [X/10]
            - Domain Taxonomy: [Candidate Domain] vs [JD Domain]
            - Logistics Status: [Candidate Location] vs [JD Location/Work Mode]
            - Recency Check: [Pass/Fail for 5/10 year rules]
            - Strict Reason for Score: (Explicitly mention Domain and Location alignment)
            - Top 3 Relevant Assets: (Must be < 5 years old)
            - Top 3 Gaps/Irrelevancies: (Include domain mismatches or outdated experience)
        """)

    resume = get_resume("resume.txt")

    # Get job description from linkedin using linkedin_loader.py. This is from linkedin public page.
    # job_details = get_linkedin_job_public("https://www.linkedin.com/jobs/view/4354044808/")
    # Get the job description from the job_details dictionary.
    # job_details_description = job_details["description"]

    # Get job description from linkedin using linkedin_loader_private.py. This is from linkedin private page.
    # This allows us to know whether the candidate has applied to
    job = get_linkedin_job(job_url)
    
    # Check if the job is open, applied, or closed.
    if job.status == "applied" or job.status == "closed":
        print("The candidate has applied to the job or the job is closed.")
    else:
        job_details_description = job.description
        job_details_title = job.title
        
        # get today's date, so the LLM knows the current date.
        today_date = date.today()

        user_message = f"""
        Today's date: {today_date}
        Conduct a rigorous gap analysis between the following resume and job description.:

        Resume: {resume}
        
        Job Title: {job_details_title}
        Job Description: {job_details_description}
        """
            
        results = agent.invoke({"messages": [{"role": "user", "content": user_message}]})
        # for message in results.get("messages"):
        #     print("Agent response:", message.content)
        
        # Get the AI final response and print it
        ai_response = results.get("messages")[-1].content
        print("AI Response:", ai_response)


def main():
    match_job("https://www.linkedin.com/jobs/view/4365177577/")

if __name__ == "__main__":
    main()


