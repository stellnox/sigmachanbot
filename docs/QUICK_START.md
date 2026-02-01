# 🚀 SigmaChanBot - Quick Start Guide

## One-Time Setup

### 1. Get Your Credentials
- **Telegram User ID**: Send `/start` to the bot (it will show your ID)
- **API_ID & API_HASH**: Go to https://my.telegram.org/apps
- **BOT_TOKEN**: Talk to @BotFather, create new bot, copy token

### 2. Create .env File
```bash
cp .env.example .env
nano .env
```

Add your credentials:
```
API_ID=123456789
API_HASH=abcdef...your_hash...
BOT_TOKEN=1234567890:ABCdef...your_token...
```

### 3. Activate Virtual Environment
```bash
source venv/bin/activate
```

## Daily Usage

### Start Bot
```bash
./control.sh start
```

### Stop Bot
```bash
./control.sh stop
```

### View Logs
```bash
./control.sh logs
```

### Restart Bot
```bash
./control.sh restart
```

## Control Your Groups

### Step 1: Add Group to Managed List (DM Bot)
```
/addgroup -1001234567890 GroupName
```

Get group ID from group info or forward a message from group to @userinfobot

### Step 2: Make Bot Admin in Group
1. Add bot to your group
2. Make bot an admin
3. Give permissions: Restrict members, Delete messages

### Step 3: Use Group Commands

**Mute User** (reply to their message):
```
/mute
```

**Unmute User**:
```
/unmute
```

**Kick User**:
```
/kick
```

**Ban User**:
```
/ban
```

**Get Group Info**:
```
/groupinfo
```

## Useful Commands (Private Chat)

- `/start` - Welcome & get your user ID
- `/help` - All available commands
- `/addgroup` - Add group to managed list
- `/listgroups` - View all managed groups
- `/admin` - Admin panel

## Troubleshooting

**Q: Bot not responding?**
- Check: `./control.sh status`
- View logs: `./control.sh logs`
- Restart: `./control.sh restart`

**Q: "Admin only" error?**
- Your user ID must be in `config.py` ADMINS list
- Get your ID: `/start` command

**Q: Can't mute/kick/ban users?**
1. Make sure bot is admin in the group
2. Give bot all admin permissions
3. Verify you're admin in the group
4. Try the command again

**Q: Group not found error?**
- Use `/listgroups` to see managed groups
- Get correct group ID and try `/addgroup` again

## File Locations

- **Bot Code**: `bot.py`
- **Config**: `config.py` (edit ADMINS here)
- **Logs**: `bot.log` (auto-created)
- **Groups DB**: `managed_groups.json` (auto-created)

## Tips

✅ Always use `/start` to get your user ID  
✅ Keep bot running with `./control.sh start`  
✅ Check logs if something goes wrong  
✅ Make sure bot is admin before using group commands  
✅ Reply to user's message for mute/kick/ban  

---

**Need more help?** Check README.md for full documentation.
