import os
from dotenv import load_dotenv

# Get langchain dependencies
from langchain.agents import create_agent
from langchain_google_genai import ChatGoogleGenerativeAI

from get_resume import get_resume
# from url_loader import get_linkedin_job
from linkedin_loader import get_linkedin_job_public

from datetime import date

load_dotenv()

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")


def initialize_agent():
    model = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0)

    agent = create_agent(
        model=model,
        tools=[],
        system_prompt="""
        Role: You are a highly critical Technical Executive Recruiter. You use a "Strict Domain Exclusion" policy to ensure specialized roles are not filled by generalists or adjacent-domain candidates.

        Task: Categorize and compare a [Job Description] and a [Resume] based on the following output format:

        Step 1: Domain Taxonomy (The "Hard Fail" Check) Before scoring, identify the primary domain for both the JD and the Resume from this list: [Product/AppDev, Infrastructure/Platform, Data Engineering, ML/AI, Security].
           - Constraint: If the JD is "Infrastructure/Platform" and the Resume is "Data Engineering" (even if it says "Data Platform"), this is a Domain Mismatch.
           - Logic: Data platforms focus on pipelines (Spark, Airflow, Warehousing); Infrastructure platforms focus on cloud primitives (K8s, Terraform, Developer Experience). They are not interchangeable.

        Step 2: Scoring Rubric (Strict Enforcement):
        - 1-3 (Mismatch): The candidate’s primary leadership domain over the last 5 years does not match the JD domain. (e.g., A Data Leader applying for an Infra/Platform role is an automatic 3 or lower, regardless of seniority).
        - 4-6 (Adjacent/Stale): Correct domain but the technical stack or leadership impact is older than 5 years.
        - 7-10 (Targeted Match): High domain alignment AND recent (last 5 years) leadership in that specific stack.

        Evaluation Constraints:
        - Recency Penalty: If the candidate has not managed the specific domain in the last 5 years, the maximum score is 5.
        - Leadership Recency: No credit for management experience older than 10 years.
        - Specific Accomplishments: Only weight accomplishments from the last 5 years.
        - Strict Reason for Score: (Focus specifically on why the domain matches or fails)
        - Recency Audit: [List most recent relevant leadership role and year]

        Output Format:
        - Overall Match Score: [X/10]
        - Domain Alignment: [candidate domain vs JD domain]
        - Top 3 Relevant Assets: (recent only)
        - Top 3 Gaps/Irrelevancies: (include outdated skills)
        - Recency Check: [Pass/Fail for 5/10 year rules]
        """)

    resume = get_resume("resume.txt")

    # job_description = get_linkedin_job("https://www.linkedin.com/jobs/view/4358994928/")
    job_details = get_linkedin_job_public("https://www.linkedin.com/jobs/view/4362429583/")
    job_details_description = job_details["description"]
    today_date = date.today()

    user_message = f"""
    Today's date: {today_date}
    Conduct a rigorous gap analysis between the following resume and job description.:

    Resume: {resume}
    
    Job Description: {job_details_description}
    """
        
    results = agent.invoke({"messages": [{"role": "user", "content": user_message}]})
    # for message in results.get("messages"):
    #     print("Agent response:", message.content)
    
    # Get the AI final response and print it
    ai_response = results.get("messages")[-1].content
    print("AI Response:", ai_response)


def main():
    initialize_agent()

if __name__ == "__main__":
    main()


