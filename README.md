# 🍽 RecipeBot — AI Recipe Assistant for Telegram

RecipeBot is a Telegram chatbot that suggests personalized recipes based on ingredients you have at home.
It tracks dietary preferences, allergens, and conversation history to provide relevant, safe, and structured cooking ideas with calorie estimates.

---

## ✨ Features

| Feature | Description |
|---|---|
| 🥘 Ingredient-based recipes | Send a list of ingredients → get 2–3 full recipes |
| 🔢 Calorie estimation | Each dish includes approximate kcal per serving |
| ⚠️ Allergen control | Bot never uses ingredients marked as allergens |
| 🥗 Dietary modes | Supports regular, vegetarian, and vegan diets |
| 🧠 User memory | Remembers liked dishes and conversation history |
| 💬 Context awareness | Understands follow-up messages within a session |
| 🔄 Model fallback | Automatically switches to available free AI model if one fails |
| 🤖 AI-powered | Uses OpenRouter API with free LLM models |

---

## 📁 Project Structure

```
RecipeBot/
├── bot.py              # Main Telegram bot logic and handlers
├── storage.py          # JSON-based user profile storage system
├── requirements.txt    # Python dependencies
├── users.json          # Auto-generated user database (git-ignored)
└── README.md           # Project documentation
```

---

## 🚀 Quick Start

### 1. Clone the repository

```bash
git clone https://github.com/>>>/recipe""".git
cd RecipeBot
```

### 2. Create a virtual environment

```bash
python -m venv .venv

# macOS / Linux
source .venv/activate

# Windows
.venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Set your API keys

Open `bot.py` and replace the placeholder values:

```python
TELEGRAM_TOKEN=your_telegram_bot_token
OPENROUTER_API_KEY=your_openrouter_api_key
```

- Get Telegram token from [@BotFather](https://t.me/BotFather)
- Get OpenRouter key from [openrouter.ai](https://openrouter.ai)

### 5. Run the bot

```bash
python bot.py
```

---

## 📦 Dependencies

```
python-telegram-bot==21.x
openai
```

See full list in `requirements.txt`.

---

## 🤖 Bot Commands

| Command | Description |
|---|---|
| `/start` | Start the bot and see welcome message |
| `/help` | Show usage instructions |
| `/allergy` | Set allergens (e.g. nuts, milk, gluten) |
| `/diet` | Choose diet: regular / vegetarian / vegan |
| `/profile` | View your saved profile |
| `/reset` | Clear conversation history |
| `/cancel` | Cancel current operation |

---

## 🧠 How It Works

1. User sends a list of ingredients (e.g. `chicken, rice, onion, garlic`)
2. Bot builds a personalized system prompt based on the user's diet, allergens, and liked dishes
3. Request is sent to OpenRouter — it tries free models one by one until one responds
4. AI returns 2–3 structured recipes with calorie info and step-by-step instructions
5. Bot saves conversation history and liked dish names for future personalization

---

## 🛠 Tech Stack

- **Python 3.11+**
- **python-telegram-bot v21** — Telegram Bot API wrapper
- **OpenRouter** — unified API for free LLM models
- **LLM Models** — openrouter/free router (auto-selects available free model)
- **JSON file** — lightweight storage for user profiles

---

## 🛡 Error Handling

- **Allergen safety** — allergens are hardcoded into the AI system prompt as forbidden ingredients
- **Model fallback** — if one free model returns 429 (rate limit) or 404 (unavailable), the bot automatically tries the next model in the list
- **Thinking mode filter** — strips internal model reasoning (`<think>` blocks) before sending to user
- **Rate limit for users** — users must wait 5 seconds between requests
- **Conversation history limit** — capped at last 6 messages to prevent token overflow

---

## 👥 Team Contributions

| Member | Contribution |
|---|---|
| Member 1 | Telegram bot architecture, command handlers, conversation flows |
| Yenlik | AI prompt engineering, personalization logic, model fallback system |
| Aibol | User storage system (storage.py), error handling, testing |

---

## 📌 Possible Improvements

- Inline buttons for recipe selection
- `/favorites` command to save specific recipes
- Weekly meal planner
- Full nutrition breakdown (protein / carbs / fats)
- Dish image generation
- Web dashboard for user profiles

---

## 📝 License

MIT License — free to use and modify.
