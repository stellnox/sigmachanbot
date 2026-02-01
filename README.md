# 🤖 SigmaChanBot

A robust Telegram bot with comprehensive group management capabilities.

## ⚡ Quick Start

```bash
# 1. Setup
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 2. Configure
cp .env.example .env
# Edit .env with your credentials

# 3. Run
./control.sh start
```

**📖 Full guide**: See `docs/QUICK_START.md`

## ✨ Features

- 🔇 **Mute/Unmute** users in groups
- 👢 **Kick/Ban** users from groups
- 📊 **Group Management** - Add/remove/list managed groups
- 🔐 **Admin Controls** - Secure admin-only commands
- 📝 **Auto Logging** - All actions logged
- 💾 **Persistent Storage** - Groups saved in JSON
- ⚡ **No Webhooks** - Long polling, runs locally

## 🎯 Commands

### Private Chat
```
/start                       Get your user ID
/help                        List all commands
/addgroup                    Add group to manage
/removegroup                 Remove managed group
/listgroups                  Show managed groups
/admin                       Admin panel
/say <chat_id> <text>        Send text as bot to a chat (admin only)
/send_photo <chat_id> (reply)  Copy a replied photo to target chat (admin only)
/send_video <chat_id> (reply)  Copy a replied video to target chat (admin only)
/send_document <chat_id> (reply)  Copy a replied document to target chat (admin only)
/broadcast <text>            Broadcast text to all managed groups (admin only)
/reply <user_id> <text>      Send a DM to a user as the bot (admin only)
```

### In Groups (requires admin)
```
/mute             Mute user (reply to message)
/unmute           Unmute user (reply to message)
/kick             Kick user (reply to message)
/ban              Ban user (reply to message)
/groupinfo        Get group information
/say <text>       Send text as bot to this chat (group admins)
/send_photo (reply)  Copy a replied photo into this chat (group admins)
/send_video (reply)  Copy a replied video into this chat (group admins)
/send_document (reply)  Copy a replied document into this chat (group admins)
```

## 🛠️ Bot Control

```bash
./control.sh start      # Start bot
./control.sh stop       # Stop bot
./control.sh restart    # Restart bot
./control.sh status     # Show status
./control.sh logs       # View live logs
```

## 📁 Project Structure

```
sigmachanbot/
├── bot.py                      Main bot code
├── config.py                   Configuration
├── control.sh                  Bot control script
├── requirements.txt            Dependencies
├── .env                        Your credentials (create from .env.example)
├── .env.example               Credentials template
├── .gitignore                 Git rules
├── README.md                  This file
├── docs/                      Documentation
│   ├── QUICK_START.md        5-minute setup
│   ├── FEATURES.md           Full feature list
│   └── STRUCTURE.md          Project structure
├── venv/                      Python environment
└── managed_groups.json        Group database (auto-created)
```

## ⚙️ Configuration

Edit `config.py` to set:
- **ADMINS** - Your admin user ID (get from `/start`)
- **BOT_USERNAME** - Your bot's username
- **BOT_NAME** - Bot display name

## 🔐 Setup Requirements

1. **Get API Credentials**
   - API_ID & API_HASH from https://my.telegram.org/apps
   - BOT_TOKEN from @BotFather on Telegram

2. **Configure Bot**
   - Copy `.env.example` to `.env`
   - Add your credentials
   - Add your user ID to `config.py` ADMINS

3. **Group Permissions**
   - Make bot admin in groups
   - Give bot these permissions:
     - Restrict members
     - Delete messages
     - Manage group info

## 📚 Documentation

- **QUICK_START.md** - Get started in 5 minutes
- **FEATURES.md** - Complete feature reference
- **STRUCTURE.md** - File organization guide

Start with `docs/QUICK_START.md` →

## 🐛 Troubleshooting

| Issue | Solution |
|-------|----------|
| Bot not responding | Run `./control.sh logs` to check errors |
| "Admin only" error | Add your ID to ADMINS in config.py |
| Permission denied | Make bot admin in the group |
| Can't mute/kick users | Verify bot has required permissions |

## 💡 Tips

✅ Use `/start` to find your user ID  
✅ Keep bot running with `./control.sh start`  
✅ Check logs if something fails  
✅ Make bot admin BEFORE using group commands  

## 📄 License

This project is provided as-is for personal use.


Or upgrade pip first (recommended):
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### Step 4: Configure Environment Variables

1. Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

2. Edit `.env` and add your credentials:
```bash
nano .env
```

Add your values:
```
API_ID=your_api_id_here
API_HASH=your_api_hash_here
BOT_TOKEN=your_bot_token_here
```

**How to get these values:**
- **API_ID & API_HASH:** Visit https://my.telegram.org → API development tools
- **BOT_TOKEN:** Message @BotFather on Telegram → /newbot

### Step 5: Add Admin IDs (Optional)

Edit `config.py` and add your Telegram user ID to the `ADMINS` list:

```python
ADMINS = [
    123456789,  # Your user ID
]
```

To find your user ID, run the bot and send `/start` - check the logs.

## Running the Bot

### Start the Bot

```bash
python bot.py
```

You should see:
```
🚀 Starting SigmaChanBot...
✅ SigmaChanBot started successfully!
```

### Stop the Bot

Press `Ctrl + C` in the terminal.

### Deactivate Virtual Environment

```bash
deactivate
```

## Project Structure

```
sigmachanbot/
├── bot.py              # Main bot file with command handlers
├── config.py           # Configuration and credentials
├── requirements.txt    # Python dependencies
├── .env.example        # Environment template
└── README.md          # This file
```

## File Descriptions

### `bot.py`
Main bot file with:
- Pyrogram Client initialization
- `/start` command handler
- `/help` command handler  
- `/admin` command (admin only)
- `is_admin()` function for permission checking
- Logging system

### `config.py`
Configuration file with:
- Environment variable loading
- API credentials (API_ID, API_HASH, BOT_TOKEN)
- Admin user IDs list
- Bot settings

### `requirements.txt`
Python dependencies:
- `pyrogram` - Telegram bot framework
- `tgcrypto` - Encryption support
- `python-dotenv` - Load environment variables

### `.env.example`
Template for environment variables (rename to `.env`)

## Available Commands

| Command | Description | Who Can Use |
|---------|-------------|------------|
| `/start` | Welcome message | Everyone |
| `/help` | Help information | Everyone |
| `/admin` | Admin panel | Admins only |
| `/say` | Send text to a chat or in-group as bot | Admins / Group Admins |
| `/send_photo` | Copy a replied photo to a chat | Admins / Group Admins |
| `/send_video` | Copy a replied video to a chat | Admins / Group Admins |
| `/send_document` | Copy a replied document to a chat | Admins / Group Admins |
| `/broadcast` | Broadcast text to all managed groups | Admins only |
| `/reply` | Send DM to a user from the bot | Admins only |

## Troubleshooting

### "ModuleNotFoundError: No module named 'pyrogram'"
**Solution:** Make sure virtual environment is activated and requirements are installed:
```bash
source venv/bin/activate
pip install -r requirements.txt
```

### "Error: API_ID is 0"
**Solution:** Check that `.env` file exists in the same directory as `bot.py` and contains your credentials.

### "Connection failed"
**Solution:** 
- Check your internet connection
- Verify API credentials are correct
- Make sure BOT_TOKEN is valid

### "InvalidSessionString"
**Solution:** Delete any `.session` files and restart the bot.

## Editing the Bot

Edit the commands in `bot.py` by modifying the handler functions:

```python
@app.on_message(filters.command("mycommand"))
async def my_command(client: Client, message: Message):
    await message.reply_text("Your response")
```

## Next Steps

1. ✅ Set up the bot locally
2. ✅ Test basic commands
3. 📝 Add your own custom commands
4. 📹 Implement batch management features
5. 🚀 Consider hosting options (optional)

## Resources

- **Pyrogram Docs:** https://docs.pyrogram.org
- **Telegram Bot API:** https://core.telegram.org/bots/api
- **BotFather Guide:** Message @BotFather on Telegram

## Notes

- The bot runs with **long polling** (no webhooks)
- All sessions are stored locally
- Sensitive data is loaded from `.env` (never commit this file!)
- The bot logs all activities for debugging

## Support

For issues or questions:
1. Check the troubleshooting section
2. Review the code comments
3. Check Pyrogram documentation

---

**Happy botting! 🚀**
