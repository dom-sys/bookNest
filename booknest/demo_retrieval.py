"""Run from the repository folder: python3 -m booknest.demo_retrieval"""

from .retrieval import find_passages


# Original sample text, used only to demonstrate retrieval.
SAMPLE_CHAPTERS = [
    [
        "Mira found a brass key beside the bookshop window.",
        "Jonah carried a box of poetry books into the shop.",
    ],
    [
        "Mira used the brass key to open a locked cabinet.",
        "Inside the cabinet was a map of the old railway station.",
    ],
    [
        "At the railway station, Jonah discovered a hidden library.",
    ],
]


def main():
    question = "Who found the brass key?"
    completed_chapter = 1
    print(f"Question: {question}")
    print(f"Completed chapter: {completed_chapter}\n")
    passages = find_passages(SAMPLE_CHAPTERS, completed_chapter, question)
    if not passages:
        print("No matching passages were found in the completed chapters.")
    for passage in passages:
        print(f"[{passage['source']}]")
        print(passage["text"])
        print()


if __name__ == "__main__":
    main()
