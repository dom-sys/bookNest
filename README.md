#BookNest 

BookNest in an AI-enabled desktop bookstore application built with Python and Tkinter. It stores data locally using JSONL files and transaction journal. 


##Feautures 
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
## Run BookNest

With the virtual environment activated, run:

```bat
python -m booknest --seed
```
