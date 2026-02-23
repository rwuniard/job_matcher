class JobMatcherResult:
    def __init__(self, job_url: str, job_status: str, ai_response: str, job_description: str = ""):
        """
        Args:
            job_url: The URL of the job to match.
            job_status: The status of the job ("open", "applied", "closed").
            ai_response: The AI response to the job matching.
            job_description: The full job description text.
        """
        self.job_url = job_url
        self.job_status = job_status
        self.ai_response = ai_response
        self.job_description = job_description

    def __str__(self):
        return f"JobMatcherResult(job_result={self.job_status}, url={self.job_url}, ai_response={self.ai_response})"

    def to_json(self):
        """
        Convert the job matching result to a JSON object.
        Returns:
            A JSON object containing the job result and AI response.
        """
        return {
            "job_result": self.job_status,
            "job_url": self.job_url,
            "ai_response": self.ai_response,
            "job_description": self.job_description,
        }