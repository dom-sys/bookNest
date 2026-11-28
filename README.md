# BookNest 

BookNest is an AI-enabled desktop bookstore application built with Python and Tkinter. It stores data locally using JSONL files and transaction journal. 


## Features 
- User registration and face-based authentication
- Administrator recovery and account management
- Book browsing, search, and recommendations
- Shopping cart, purchases, prepaid balances, and VIP discounts
- Reviews, taboo-word filtering, warnings, and suspension
- Local AI assistant and chapter-limited Ask-the-Book retrieval

## Requirements

- Python 3.11 or newer
- Tkinter
- A webcam for face enrollment and login
- Optional: Ollama for model-generated answers

On some Linux distributions, Tkinter requires a separate operating-system package, such as `python3-tk`.

## Windows Setup

Download and extract the repository. Open Command Prompt in the folder containing `requirements-face.txt`.

```bat
py -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements-face.txt
```

## Run BookNest

```bat
python -m booknest --seed
```
