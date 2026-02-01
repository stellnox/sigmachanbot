# 📁 Project Structure

```
sigmachanbot/
│
├── 🤖 CORE BOT FILES
│   ├── bot.py                      # Main bot code (all handlers & logic)
│   └── config.py                   # Configuration & credentials loader
│
├── 📚 DOCUMENTATION
│   ├── README.md                   # Full documentation
│   ├── QUICK_START.md              # 5-minute setup guide
│   ├── FEATURES.md                 # Complete feature list
│   └── STRUCTURE.md                # This file
│
├── ⚙️ CONTROL & MANAGEMENT
│   ├── control.sh                  # Bot control script (start/stop/restart)
│   └── requirements.txt            # Python dependencies
│
├── 🔐 ENVIRONMENT
│   ├── .env                        # Your credentials (create from .env.example)
│   ├── .env.example                # Template for .env
│   └── .gitignore                  # Git ignore rules
│
├── 📊 DATA & LOGS
│   ├── bot.log                     # Bot execution logs (auto-created)
│   ├── managed_groups.json         # Managed groups database (auto-created)
│   └── sigmachanbot_session.session # Bot session file (auto-created)
│
└── 🐍 VIRTUAL ENVIRONMENT
    └── venv/                       # Python virtual environment

```

## 📝 File Descriptions

### Core Files

**`bot.py`** (425+ lines)
- Main bot implementation
- All command handlers (@app.on_message decorators)
- Group management functions (mute, kick, ban, etc.)
- Error handling and logging
- Database operations for groups

**`config.py`** (35 lines)
- Loads credentials from .env
- Defines admin list
- Bot display settings
- Database file location

### Documentation Files

**`README.md`** (100+ lines)
- Complete installation guide
- Full command reference
- Configuration instructions
- Troubleshooting section
- Security information

**`QUICK_START.md`** (80+ lines)
- Quick setup in 5 minutes
- Daily usage commands
- Group control step-by-step
- Common troubleshooting
- Quick tips and tricks

**`FEATURES.md`** (150+ lines)
- Detailed feature descriptions
- Command reference table
- Technical stack information
- Scalability information
- Usage scenarios
- Future enhancement ideas

**`STRUCTURE.md`** (This file)
- Project file organization
- File descriptions
- Quick reference guide

### Control Files

**`control.sh`** (Executable)
Commands:
- `./control.sh start` - Start bot
- `./control.sh stop` - Stop bot
- `./control.sh restart` - Restart bot
- `./control.sh status` - Show status
- `./control.sh logs` - View logs

**`requirements.txt`**
```
pyrogram==2.0.106
TgCrypto==1.2.5
python-dotenv==1.0.0
```

### Environment Files

**`.env`** (Template-based, create from .env.example)
```
API_ID=your_api_id
API_HASH=your_api_hash
BOT_TOKEN=your_bot_token
```

**`.env.example`** (Template)
Shows what variables you need in .env

**`.gitignore`**
Prevents tracking of:
- venv/ (virtual environment)
- .env (credentials)
- __pycache__/ (Python cache)
- *.session* (session files)
- *.log (log files)

### Auto-Generated Files

**`bot.log`** (Created when bot runs)
Contains:
- Startup messages
- Command logs
- Error messages
- User actions
View with: `tail -f bot.log`

**`managed_groups.json`** (Created on first use)
Example:
```json
{
  "-1001234567890": {
    "name": "Study Group",
    "restrictions": []
  },
  "-1001234567891": {
    "name": "Gaming Guild",
    "restrictions": []
  }
}
```

**`sigmachanbot_session.session`**
- Bot authentication
- Persists login between restarts
- Auto-managed by Pyrogram

### Virtual Environment

**`venv/`** (Python virtual environment)
Contains:
- Python interpreter
- Installed packages (pyrogram, etc.)
- Site-packages directory

Created with: `python3 -m venv venv`

## 🚀 Quick Reference

### Start Working
```bash
cd /home/ingit/projects/telegram_bots/sigmachanbot
source venv/bin/activate
```

### See What's Running
```bash
./control.sh status
```

### View Live Logs
```bash
./control.sh logs
```

### Restart After Changes
```bash
./control.sh restart
```

### View Configuration
```bash
cat config.py        # See config
cat .env             # See credentials
```

### Check Managed Groups
```bash
cat managed_groups.json
```

## 📊 File Statistics

| File | Type | Purpose | Size |
|------|------|---------|------|
| bot.py | Python | Bot logic | ~425 lines |
| config.py | Python | Configuration | ~35 lines |
| control.sh | Shell | Management | ~70 lines |
| README.md | Doc | Full guide | ~100 lines |
| QUICK_START.md | Doc | Quick guide | ~80 lines |
| FEATURES.md | Doc | Features | ~150 lines |
| requirements.txt | Config | Dependencies | 3 lines |
| .gitignore | Config | Git rules | ~30 lines |

## 🔄 Typical Workflow

1. **First Time Setup**
   - Copy .env.example to .env
   - Add credentials
   - Run `./control.sh start`

2. **Daily Use**
   - `./control.sh start` (morning)
   - Use bot commands in Telegram
   - `./control.sh stop` (if needed)

3. **Maintenance**
   - Check logs: `./control.sh logs`
   - Add groups: `/addgroup`
   - Monitor: `/listgroups`

4. **Changes**
   - Edit config.py or bot.py
   - Run `./control.sh restart`
   - Check logs for errors

## 🎯 Next Steps

1. **Read QUICK_START.md** - Get up and running
2. **Set up .env** - Add your credentials
3. **Start bot** - `./control.sh start`
4. **Send /start** - Test in Telegram
5. **Add groups** - `/addgroup`
6. **Control users** - Use /mute, /kick, /ban

---

**Everything is organized and ready to use! 🎉**
