

def get_resume(filename: str) -> str:
    with open(filename, "r") as file:
        return file.read()

if __name__ == "__main__":
    print(get_resume("resume.txt"))