<div align="center">

# 🎫 AuraFlex Ticket Bot

### *The Ultimate Discord Ticket System with Groq AI*

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![discord.py](https://img.shields.io/badge/discord.py-2.3%2B-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://discordpy.readthedocs.io)
[![Groq AI](https://img.shields.io/badge/Groq_AI-Llama_3.1-FF6B35?style=for-the-badge&logo=meta&logoColor=white)](https://console.groq.com)
[![License](https://img.shields.io/badge/License-MIT-57F287?style=for-the-badge)](LICENSE)

**A powerful, feature-rich Discord ticket bot powered by Groq AI.**
**AI automatically helps users until a staff member claims the ticket.**

---

[✨ Features](#-features) • [🚀 Setup](#-quick-setup) • [📖 Commands](#-commands) • [🤖 AI System](#-ai-system) • [⚙️ Configuration](#%EF%B8%8F-configuration)

</div>

---

## ✨ Features

### 🎫 Ticket System
- **Multi-category tickets** with dropdown selection
- **6 default categories** (General, Billing, Bug, Suggestion, Partnership, Application)
- **Custom categories** — add/remove any time
- **Ticket numbering** — every ticket gets a unique `#0001` ID
- **Per-user ticket limits** — prevent spam (1-10 max)
- **Ticket blacklist** — block specific users

### 🤖 AI Assistant (Groq Llama 3.1)
- **Auto-responds** to users in unclaimed tickets
- **Pauses instantly** when a staff member claims the ticket
- **Resumes** if ticket is unclaimed
- **Context-aware** — remembers conversation history (last 15 messages)
- **Server-aware** — teach it your server's rules, products, info
- **Step-by-step answers** — explains Discord features, troubleshoots issues

### 🛡️ Staff Tools
- **Claim system** — staff can take ownership of tickets
- **Priority levels** — 🟢 Low / 🟡 Medium / 🟠 High / 🔴 Critical
- **Transcript export** — save full chat history as `.txt`
- **Force close** — admin override to close any ticket
- **Close all** — bulk close all open tickets
- **Add/Remove users** — guest access management
- **Transfer ownership** — move ticket to another user

### 📋 Logging & Transcripts
- **Full action logging** — every action logged to a channel
- **Auto-transcript** — saved automatically on ticket close/delete
- **DM notifications** — users get DM'd when ticket closes
- **Feedback system** — star rating + comments via DM

### ⚙️ Configuration
- **Interactive setup wizard** — dropdown-based, no commands needed
- **10+ toggle-able features** — enable/disable anything
- **Custom welcome messages** — with `{user}` and `{server}` variables
- **Custom close messages**
- **Auto-close timer** — close inactive tickets automatically
- **Persistent views** — buttons work after bot restart

---

## 📋 Requirements

| Requirement | Version |
|-------------|---------|
| Python | 3.10+ |
| discord.py | 2.3.0+ |
| aiohttp | 3.9.0+ |
| Groq API Key | Free at [console.groq.com](https://console.groq.com) |
| Discord Bot Token | [discord.com/developers](https://discord.com/developers/applications) |

---

## 🚀 Quick Setup

Step 1 — pip install -r requirements.txt 
Step 2 — python main.py
Step 3 — Enjoy!! 
