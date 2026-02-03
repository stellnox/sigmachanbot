"""
SigmaChanBot - Robust Telegram Bot with Group Management
"""
import logging
import json
import os
import asyncio
from pyrogram import Client, filters, idle
from pyrogram.types import (
    Message,
    ChatPermissions,
    BotCommand,
    BotCommandScopeChat,
    BotCommandScopeChatAdministrators,
)
from pyrogram.errors import UserNotParticipant, UserAlreadyParticipant, ChatAdminRequired
from config import API_ID, API_HASH, BOT_TOKEN, ADMINS, SESSION_NAME, SESSION_DIR, BOT_USERNAME, BOT_NAME
from typing import Optional

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

GROUPS_DB = "managed_groups.json"
USERS_DB = "users.json"
MESSAGES_DB = "messages.json"
TOPICS_DB = "topics.json"

# Ensure data directory exists
os.makedirs(SESSION_DIR, exist_ok=True)

app = Client(
    name=SESSION_NAME,
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    workdir=SESSION_DIR
)

# ==================== Utility Functions ====================

def is_admin(user_id: int) -> bool:
    """Check if user is admin"""
    return user_id in ADMINS


async def _is_chat_admin(client: Client, chat_id: int, user_id: int) -> bool:
    """Check if a user is an admin in the given chat (includes creator/owner)."""
    try:
        member = await client.get_chat_member(chat_id, user_id)
        status = getattr(member, 'status', None)
        logger.debug(f"Chat member status: user {user_id} in chat {chat_id}, status='{status}'")
        
        # Handle different status types - convert to string for comparison
        status_str = str(status).lower() if status else ''
        
        # Admin statuses: 'administrator', 'creator', 'owner', and ChatMemberStatus enum values
        is_admin_user = (
            status_str in ('administrator', 'creator', 'owner') or
            'administrator' in status_str or
            'creator' in status_str or
            'owner' in status_str
        )
        
        logger.info(f"Admin check: {user_id} in {chat_id} = {is_admin_user} (status: {status})")
        return is_admin_user
    except Exception as e:
        logger.error(f"❌ Admin check failed for {user_id} in {chat_id}: {e}")
        return False


def _normalize_group_id(group_id_str: str) -> int:
    """Convert group ID string to proper Telegram group ID format.
    Telegram supergroup/channel IDs are stored as negative numbers: -100XXXXX"""
    try:
        gid = int(group_id_str)
        # If it's already negative, return as is
        if gid < 0:
            return gid
        # If positive, convert to Telegram supergroup format
        return -1000000000000 - gid
    except Exception:
        return int(group_id_str)


def _get_group_id_from_index(index_or_id: str) -> tuple:
    """Convert index (1,2,3) or ID to actual group ID.
    Returns (group_id_int, group_id_str, is_index_based)
    If index_or_id is an index like '1', looks it up in managed groups.
    If it's an ID (large number or negative), uses it directly."""
    try:
        val = int(index_or_id)
        groups = load_managed_groups()
        group_ids = list(groups.keys())
        
        # If it's a small positive number (1-999), treat as index
        if 1 <= val <= 999 and val <= len(group_ids):
            group_id_str = group_ids[val - 1]
            return (int(group_id_str), group_id_str, True)
        
        # Otherwise treat as direct ID
        return (val, index_or_id, False)
    except Exception:
        return (int(index_or_id), index_or_id, False)


def _get_group_index(group_id_str: str) -> int:
    """Get the index (1, 2, 3...) of a group by ID. Returns -1 if not found."""
    try:
        groups = load_managed_groups()
        group_ids = list(groups.keys())
        if group_id_str in group_ids:
            return group_ids.index(group_id_str) + 1
        return -1
    except Exception:
        return -1


async def _resolve_topic_id(client: Client, chat_id: int, topic_input: str) -> Optional[int]:
    """Resolve topic name or number to topic ID.
    
    Args:
        client: Pyrogram client
        chat_id: Chat ID to get forum topics from
        topic_input: Can be topic_123, 123, or topic name
    
    Returns:
        Topic ID as integer or None if not found
    """
    try:
        # Remove quotes if present
        clean_input = topic_input.strip('"\'')
        logger.info(f"Resolving topic '{clean_input}' (original: '{topic_input}') for chat {chat_id}")
        
        # If it's already a number (topic_123 or 123)
        if clean_input.startswith('topic_'):
            try:
                topic_id = int(clean_input.split('_')[1])
                logger.info(f"Resolved topic ID from format: {topic_id}")
                return topic_id
            except ValueError:
                pass
        elif clean_input.isdigit():
            try:
                topic_id = int(clean_input)
                logger.info(f"Resolved topic ID from number: {topic_id}")
                return topic_id
            except ValueError:
                pass
        
        # Try to resolve by name (for forum groups)
        try:
            logger.info(f"Getting forum topics for chat {chat_id}")
            
            # First try manual mapping (works with old Pyrogram)
            manual_topic_id = get_topic_id_by_name(chat_id, clean_input)
            if manual_topic_id:
                logger.info(f"Found topic by manual mapping '{clean_input}' -> ID: {manual_topic_id}")
                return manual_topic_id
            
            # Try modern Pyrogram get_forum_topics
            try:
                async for topic in client.get_forum_topics(chat_id):
                    topic_title = getattr(topic, 'title', '').lower().strip()
                    if clean_input.lower().strip() == topic_title:
                        topic_id = getattr(topic, 'id', None)
                        logger.info(f"Found topic by name '{clean_input}' -> ID: {topic_id}")
                        # Save to manual mapping for future use
                        add_topic_mapping(chat_id, topic_title, topic_id)
                        return topic_id
                    logger.debug(f"Topic '{topic_title}' doesn't match '{clean_input}'")
            except Exception as e:
                logger.debug(f"Could not get forum topics: {e}")
                    
        except Exception as e:
            logger.debug(f"Could not get forum topics for topic resolution: {e}")
        
        # Only show warning if it looks like a topic name (not a number or topic_ format)
        if not clean_input.isdigit() and not clean_input.startswith('topic_'):
            logger.debug(f"Topic '{clean_input}' not found in chat {chat_id} (may not be a topic)")
        
        return None
    except Exception as e:
        logger.error(f"Error resolving topic ID: {e}")
        return None


async def _parse_target_chat(arg: Optional[str], default_chat: Optional[int] = None) -> Optional[str]:
    """Return a chat identifier. If arg is None, return default_chat."""
    if arg:
        return arg
    return default_chat


async def set_bot_commands_for_scopes(client: Client):
    """Set bot command lists for different scopes so non-admins don't see admin commands."""
    try:
        # Basic commands for everyone
        default_cmds = [
            BotCommand("start", "Start the bot"),
            BotCommand("help", "Show help information"),
        ]

        # Admin commands shown to admins in private chats
        admin_private_cmds = default_cmds + [
            BotCommand("forward", "Forward/copy a replied message to a chat"),
            BotCommand("admin", "Open admin panel"),
            BotCommand("topics", "List topics for a managed group (use: /topics 1)"),
            BotCommand("addgroup", "Add group to managed list"),
            BotCommand("removegroup", "Remove managed group"),
            BotCommand("listgroups", "List managed groups"),
            BotCommand("editgroupname", "Edit group display name"),
            BotCommand("clearinbox", "Clear inbox messages"),
            BotCommand("say", "Send text as the bot to a chat"),
            BotCommand("send_photo", "Send or copy a photo to a chat"),
            BotCommand("send_video", "Send or copy a video to a chat"),
            BotCommand("send_document", "Send or copy a document to a chat"),
            BotCommand("broadcast", "Broadcast text to all managed groups"),
            BotCommand("reply", "Send a DM to a user as the bot"),
        ]

        # Group admin commands (for administrators in managed groups)
        group_admin_cmds = [
            BotCommand("forward", "Forward/copy a replied message to a chat"),
            BotCommand("mute", "Mute a user (reply)"),
            BotCommand("unmute", "Unmute a user (reply)"),
            BotCommand("kick", "Kick a user (reply)"),
            BotCommand("ban", "Ban a user (reply)"),
            BotCommand("unban", "Unban a user from group"),
            BotCommand("restrict", "Restrict user permissions"),
            BotCommand("unrestrict", "Remove user restrictions"),
            BotCommand("groupinfo", "Show group info"),
            BotCommand("topics", "List all topics in this group"),
            BotCommand("addtopic", "Add topic mapping (admin only)"),
            BotCommand("say", "Send text as the bot to this chat"),
            BotCommand("send_photo", "Copy a replied photo into this chat"),
            BotCommand("send_video", "Copy a replied video into this chat"),
            BotCommand("send_document", "Copy a replied document into this chat"),
        ]

        # Apply default commands
        await client.set_bot_commands(default_cmds)

        # Apply admin commands to each admin's private chat
        for admin_id in ADMINS:
            try:
                await client.set_bot_commands(admin_private_cmds, scope=BotCommandScopeChat(admin_id))
            except Exception:
                logger.warning(f"⚠️ Could not set private commands for admin {admin_id}")

        # Apply group admin commands for managed groups
        groups = load_managed_groups()
        for gid in groups.keys():
            try:
                await client.set_bot_commands(group_admin_cmds, scope=BotCommandScopeChatAdministrators(int(gid)))
            except Exception:
                logger.warning(f"⚠️ Could not set group admin commands for {gid}")

        logger.info("✅ Bot commands configured for scopes")
    except Exception as e:
        logger.error(f"❌ Error setting bot commands: {e}")

def load_managed_groups() -> dict:
    """Load managed groups from database"""
    if os.path.exists(GROUPS_DB):
        try:
            with open(GROUPS_DB, 'r') as f:
                return json.load(f)
        except:
            return {}
    return {}


def load_users() -> dict:
    if os.path.exists(USERS_DB):
        try:
            with open(USERS_DB, 'r') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def load_messages() -> dict:
    if os.path.exists(MESSAGES_DB):
        try:
            with open(MESSAGES_DB, 'r') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def load_topics() -> dict:
    """Load topic mappings from database"""
    if os.path.exists(TOPICS_DB):
        try:
            with open(TOPICS_DB, 'r') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_topics(topics: dict):
    """Save topic mappings to database"""
    with open(TOPICS_DB, 'w') as f:
        json.dump(topics, f, indent=2)


def add_topic_mapping(chat_id: int, topic_name: str, topic_id: int):
    """Add or update a topic mapping"""
    topics = load_topics()
    chat_id_str = str(chat_id)
    if chat_id_str not in topics:
        topics[chat_id_str] = {}
    topics[chat_id_str][topic_name.lower()] = topic_id
    save_topics(topics)


def get_topic_id_by_name(chat_id: int, topic_name: str) -> Optional[int]:
    """Get topic ID by name from manual mapping"""
    topics = load_topics()
    chat_id_str = str(chat_id)
    if chat_id_str in topics:
        return topics[chat_id_str].get(topic_name.lower())
    return None


def save_messages(messages: dict):
    with open(MESSAGES_DB, 'w') as f:
        json.dump(messages, f, indent=2)


def add_message_record(msg: Message) -> int:
    """Store an incoming message and return its index id."""
    try:
        messages = load_messages()
        # ensure existing numeric keys; ignore any invalid keys
        numeric_keys = [int(k) for k in messages.keys() if k.isdigit()]
        idx = max(numeric_keys, default=0) + 1
        # prepare date as integer timestamp
        try:
            date_ts = int(msg.date.timestamp()) if getattr(msg, 'date', None) else int(__import__('time').time())
        except Exception:
            date_ts = int(__import__('time').time())

        record = {
            "id": idx,
            "message_id": getattr(msg, 'message_id', None),
            "chat_id": getattr(getattr(msg, 'chat', None), 'id', None),
            "chat_title": getattr(getattr(msg, 'chat', None), 'title', None) or getattr(getattr(msg, 'chat', None), 'first_name', None),
            "from_id": getattr(getattr(msg, 'from_user', None), 'id', None),
            "from_username": getattr(getattr(msg, 'from_user', None), 'username', None),
            "from_first": getattr(getattr(msg, 'from_user', None), 'first_name', None),
            "text": (msg.text or getattr(msg, 'caption', None) or '') if msg else '',
            "date": date_ts,
            "handled": False,
            "handled_by": None,
            "handled_at": None,
        }
        messages[str(idx)] = record
        save_messages(messages)
        return idx
    except Exception as e:
        logger.error(f"Couldn't add message record: {e}")
        # fallback: try to append with timestamp-based id to avoid returning 0
        try:
            messages = load_messages()
            idx = int(__import__('time').time())
            while str(idx) in messages:
                idx += 1
            record = {
                "id": idx,
                "message_id": getattr(msg, 'message_id', None),
                "chat_id": getattr(getattr(msg, 'chat', None), 'id', None),
                "chat_title": getattr(getattr(msg, 'chat', None), 'title', None) or getattr(getattr(msg, 'chat', None), 'first_name', None),
                "from_id": getattr(getattr(msg, 'from_user', None), 'id', None),
                "from_username": getattr(getattr(msg, 'from_user', None), 'username', None),
                "from_first": getattr(getattr(msg, 'from_user', None), 'first_name', None),
                "text": (msg.text or getattr(msg, 'caption', None) or '') if msg else '',
                "date": int(__import__('time').time()),
                "handled": False,
                "handled_by": None,
                "handled_at": None,
            }
            messages[str(idx)] = record
            save_messages(messages)
            return idx
        except Exception as e2:
            logger.error(f"Fallback saving message failed: {e2}")
            return -1


def mark_message_handled(idx: int, admin_id: int):
    try:
        messages = load_messages()
        key = str(idx)
        if key in messages:
            messages[key]['handled'] = True
            messages[key]['handled_by'] = admin_id
            messages[key]['handled_at'] = int(__import__('time').time())
            save_messages(messages)
            return True
    except Exception as e:
        logger.debug(f"Couldn't mark message handled: {e}")
    return False


def save_users(users: dict):
    with open(USERS_DB, 'w') as f:
        json.dump(users, f, indent=2)


def record_user_interaction(user, chat=None):
    try:
        users = load_users()
        uid = str(user.id)
        users[uid] = {
            "id": user.id,
            "first_name": getattr(user, 'first_name', '') or '',
            "username": getattr(user, 'username', '') or '',
            "last_seen": int(__import__('time').time()),
            "last_chat": getattr(chat, 'id', None) if chat else None,
        }
        save_users(users)
    except Exception as e:
        logger.debug(f"Couldn't record user interaction: {e}")

def save_managed_groups(groups: dict):
    """Save managed groups to database"""
    with open(GROUPS_DB, 'w') as f:
        json.dump(groups, f, indent=2)

def add_managed_group(group_id: int, group_name: str):
    """Add group to managed list"""
    groups = load_managed_groups()
    groups[str(group_id)] = {"name": group_name, "restrictions": []}
    save_managed_groups(groups)
    try:
        # update bot commands for scopes when groups change
        app.loop.create_task(set_bot_commands_for_scopes(app))
    except Exception:
        logger.debug("Couldn't schedule command-scope update")

def remove_managed_group(group_id: int):
    """Remove group from managed list"""
    groups = load_managed_groups()
    if str(group_id) in groups:
        del groups[str(group_id)]
        save_managed_groups(groups)
        try:
            app.loop.create_task(set_bot_commands_for_scopes(app))
        except Exception:
            logger.debug("Couldn't schedule command-scope update")

# ==================== Command Handlers ====================

@app.on_message(filters.command("start") & filters.private)
async def handle_start(client: Client, message: Message):
    """Start command - show welcome message"""
    try:
        user = message.from_user
        record_user_interaction(user, message.chat)
        # Show admin commands only to configured admins
        base_text = f"🎬 **Welcome, {user.first_name}!**\n\nI'm SigmaChanBot - a group management bot.\n\n"
        if is_admin(user.id):
            admin_text = (
                "**Available Commands (Admin):**\n"
                "/help - Show all commands\n"
                "/addgroup - Add a group to manage\n"
                "/listgroups - List managed groups\n"
                "/groupinfo - Get group info\n"
                "/say <chat_id> <text> - Send text as bot to a chat\n"
                "/forward <index_or_id> (reply) - Forward/copy a replied message to a managed group\n"
                "/send_photo <chat_id> (reply) - Copy/send photo\n"
                "/send_video <chat_id> (reply) - Copy/send video\n"
                "/send_document <chat_id> (reply) - Copy/send document\n"
                "/broadcast <text> - Broadcast to managed groups\n"
                "/reply <user_id> <text> - Send DM as bot\n"
            )
            await message.reply_text(base_text + admin_text)
        else:
            await message.reply_text(base_text + "Use /help to see available commands.")
        logger.info(f"✅ START: User {user.id} ({user.first_name})")
    except Exception as e:
        logger.error(f"❌ Error in start: {e}")
        await message.reply_text("❌ Error occurred")

@app.on_message(filters.command("help") & filters.private)
async def handle_help(client: Client, message: Message):
    """Help command - show all available commands"""
    try:
        user = message.from_user
        record_user_interaction(user, message.chat)
        base = (
            "📖 **Available Commands:**\n\n"
            "**General:**\n"
            "/start - Welcome message\n"
            "/help - This message\n\n"
        )

        if is_admin(user.id):
            admin_section = (
                "**Group Management (Admin only):**\n"
                "/addgroup - Add group to managed list\n"
                "/removegroup - Remove managed group\n"
                "/listgroups - Show all managed groups\n"
                "/topics - List topics in a group (use in group or /topics <index> in private)\n"
                "/forward - Forward/copy a replied message to a managed group\n"
                "/editgroupname - Edit group display name\n"
                "/groupinfo - Get info about a group\n"
                "/mute @user - Mute user (group only)\n"
                "/unmute @user - Unmute user\n"
                "/kick @user - Kick user from group\n"
                "/ban @user - Ban user from group\n"
                "/unban @user - Unban user from group\n"
                "/restrict - Restrict user permissions\n"
                "/unrestrict - Remove user restrictions\n\n"
                "**Inbox Management:**\n"
                "/clearinbox - Clear inbox messages\n\n"
                "**Admin Panel:**\n"
                "/admin - Admin panel (admin only)\n"
                "/say - Send text as the bot\n"
                "/send_photo - Send/copy photos\n"
                "/send_video - Send/copy videos\n"
                "/send_document - Send/copy documents\n"
                "/broadcast - Broadcast to managed groups\n"
                "/reply - Send DM to a user as bot\n"
            )
            await message.reply_text(base + admin_section)
        else:
            await message.reply_text(base + "Use the bot in groups or contact an admin for more features.")
        logger.info(f"✅ HELP: User {message.from_user.id}")
    except Exception as e:
        logger.error(f"❌ Error in help: {e}")

@app.on_message(filters.command("admin") & filters.private)
async def handle_admin(client: Client, message: Message):
    """Admin panel - admin only"""
    try:
        if not is_admin(message.from_user.id):
            await message.reply_text("❌ You don't have admin access")
            logger.warning(f"⚠️ Unauthorized admin access attempt by {message.from_user.id}")
            return
        
        admin_text = (
            "⚙️ **Admin Panel**\n\n"
            "Manage groups and users with the commands in /help\n"
            "You have full administrative access."
        )
        await message.reply_text(admin_text)
        logger.info(f"✅ ADMIN: User {message.from_user.id} accessed admin panel")
    except Exception as e:
        logger.error(f"❌ Error in admin: {e}")

@app.on_message(filters.command("addgroup") & filters.private)
async def handle_addgroup(client: Client, message: Message):
    """Add group to managed list"""
    try:
        if not is_admin(message.from_user.id):
            await message.reply_text("❌ Admin only")
            return
        
        # Parse command: /addgroup group_id group_name
        args = message.text.split(maxsplit=2)
        if len(args) < 2:
            await message.reply_text(
                "❌ Usage: /addgroup <group_id> [group_name]\n"
                "Example: /addgroup -1001234567890 MyGroup"
            )
            return
        
        try:
            group_id = int(args[1])
        except ValueError:
            await message.reply_text("❌ Invalid group ID")
            return
        
        group_name = args[2] if len(args) > 2 else f"Group {group_id}"
        
        add_managed_group(group_id, group_name)
        # refresh commands scoped to managed groups
        try:
            await set_bot_commands_for_scopes(client)
        except Exception:
            logger.debug("Couldn't refresh bot commands after addgroup")
        await message.reply_text(f"✅ Added group: {group_name} ({group_id})")
        logger.info(f"✅ ADDGROUP: {group_name} ({group_id})")
    except Exception as e:
        logger.error(f"❌ Error in addgroup: {e}")
        await message.reply_text("❌ Error adding group")

@app.on_message(filters.command("removegroup") & filters.private)
async def handle_removegroup(client: Client, message: Message):
    """Remove group from managed list"""
    try:
        if not is_admin(message.from_user.id):
            await message.reply_text("❌ Admin only")
            return
        
        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            await message.reply_text("❌ Usage: /removegroup <group_id>")
            return
        
        try:
            group_id = int(args[1])
        except ValueError:
            await message.reply_text("❌ Invalid group ID")
            return
        
        groups = load_managed_groups()
        if str(group_id) not in groups:
            await message.reply_text("❌ Group not found in managed list")
            return
        
        group_name = groups[str(group_id)]["name"]
        remove_managed_group(group_id)
        try:
            await set_bot_commands_for_scopes(client)
        except Exception:
            logger.debug("Couldn't refresh bot commands after removegroup")
        await message.reply_text(f"✅ Removed group: {group_name}")
        logger.info(f"✅ REMOVEGROUP: {group_name} ({group_id})")
    except Exception as e:
        logger.error(f"❌ Error in removegroup: {e}")
        await message.reply_text("❌ Error removing group")

@app.on_message(filters.command("listgroups") & filters.private)
async def handle_listgroups(client: Client, message: Message):
    """List all managed groups"""
    try:
        if not is_admin(message.from_user.id):
            await message.reply_text("❌ Admin only")
            return
        
        groups = load_managed_groups()
        if not groups:
            await message.reply_text("📭 No managed groups")
            return
        
        group_list = "📋 **Managed Groups:**\n\n"
        for i, (group_id, info) in enumerate(groups.items(), start=1):
            group_name = info.get('name', f'Group {group_id}')
            group_list += f"{i}. **{group_name}**\n   ID: `{group_id}`\n\n"
        
        group_list += f"\nTotal: {len(groups)} groups"
        await message.reply_text(group_list)
        logger.info(f"✅ LISTGROUPS: Listed {len(groups)} groups")
        record_user_interaction(message.from_user, message.chat)
    except Exception as e:
        logger.error(f"❌ Error in listgroups: {e}")
        await message.reply_text("❌ Error listing groups")


@app.on_message(filters.command("editgroupname") & filters.private)
async def handle_editgroupname(client: Client, message: Message):
    """Edit the display name of a managed group. Usage: /editgroupname <index> <new_name>"""
    try:
        if not is_admin(message.from_user.id):
            await message.reply_text("❌ Admin only")
            return
        
        args = message.text.split(maxsplit=2)
        if len(args) < 3:
            await message.reply_text("📝 Usage: /editgroupname <index> <new_name>\n\nExample: /editgroupname 1 \"My Awesome Group\"\n\nUse /listgroups to see group indices")
            return
        
        try:
            group_index = int(args[1])
            new_name = args[2].strip('"\'')
        except ValueError:
            await message.reply_text("❌ Invalid group index. Use a number.")
            return
        
        groups = load_managed_groups()
        if not groups:
            await message.reply_text("📭 No managed groups")
            return
        
        # Get group by index
        group_items = list(groups.items())
        if group_index < 1 or group_index > len(group_items):
            await message.reply_text(f"❌ Invalid group index. Use 1-{len(group_items)}")
            return
        
        group_id, group_info = group_items[group_index - 1]
        old_name = group_info.get('name', f'Group {group_id}')
        
        # Update the group name
        group_info['name'] = new_name
        groups[group_id] = group_info
        save_managed_groups(groups)
        
        await message.reply_text(
            f"✅ Group name updated:\n"
            f"**Index:** {group_index}\n"
            f"**Old Name:** {old_name}\n"
            f"**New Name:** {new_name}\n\n"
            f"Use /listgroups to see the updated list"
        )
        logger.info(f"✅ EDITGROUPNAME: {message.from_user.id} updated group {group_index} name from '{old_name}' to '{new_name}'")
        record_user_interaction(message.from_user, message.chat)
        
    except Exception as e:
        logger.error(f"❌ Error in editgroupname: {e}")
        await message.reply_text("❌ Error editing group name")


@app.on_message(filters.command("listusers") & filters.private)
async def handle_listusers(client: Client, message: Message):
    """Admin command: list recent users who interacted with the bot."""
    try:
        if not is_admin(message.from_user.id):
            await message.reply_text("❌ Admin only")
            return

        users = load_users()
        if not users:
            await message.reply_text("📭 No users recorded yet")
            return

        # Sort by last_seen desc
        sorted_users = sorted(users.values(), key=lambda u: u.get('last_seen', 0), reverse=True)
        text = "📋 **Recent Users:**\n\n"
        for i, u in enumerate(sorted_users[:50], start=1):
            uname = f"@{u['username']}" if u.get('username') else u.get('first_name','')
            text += f"{i}. {uname} — {u['id']}\n"

        text += "\nUse `/reply <index> <text>` to message a user by index or `/reply <user_id> <text>` to use id."
        await message.reply_text(text)
        record_user_interaction(message.from_user, message.chat)
    except Exception as e:
        logger.error(f"❌ Error in listusers: {e}")
        await message.reply_text("❌ Error listing users")

@app.on_message(filters.command("groupinfo") & filters.group)
async def handle_groupinfo(client: Client, message: Message):
    """Get group information (group admin only)"""
    try:
        sender = message.from_user
        if not sender:
            await message.reply_text("❌ Unable to verify user identity")
            return
        
        # Enhanced admin check with multiple fallback methods
        is_admin_check = False
        try:
            # Method 1: Direct admin check
            is_admin_check = await _is_chat_admin(client, message.chat.id, sender.id)
        except Exception as e:
            logger.error(f"❌ Primary admin check failed for groupinfo: {e}")
            try:
                # Method 2: Fallback using get_chat_member directly
                member = await client.get_chat_member(message.chat.id, sender.id)
                status = getattr(member, 'status', None)
                is_admin_check = status in ('administrator', 'creator')
                logger.info(f"📊 GROUPINFO fallback: user {sender.id} status={status} in chat {message.chat.id}")
            except Exception as e2:
                logger.error(f"❌ Fallback admin check also failed: {e2}")
                # Method 3: Check if user is in global admins list (for debugging)
                if is_admin(sender.id):
                    await message.reply_text("⚠️ You are a global admin but group admin check failed. Bot may need admin permissions in this group.")
                    return
                is_admin_check = False
        
        logger.info(f"📊 GROUPINFO: user {sender.id} admin_check={is_admin_check} in chat {message.chat.id}")
        
        if not is_admin_check:
            await message.reply_text("❌ You need to be group/channel admin to use /groupinfo\n\n💡 If you are an admin, make sure the bot also has admin permissions in this group.")
            return
        
        chat = message.chat
        info_text = (
            f"📊 **Group Information:**\n\n"
            f"**Name:** {chat.title}\n"
            f"**ID:** `{chat.id}`\n"
            f"**Members:** {getattr(chat, 'members_count', 'Unknown')}\n"
            f"**Type:** {chat.type}\n"
        )
        if chat.description:
            info_text += f"**Description:** {chat.description}\n"
        
        await message.reply_text(info_text)
        logger.info(f"✅ GROUPINFO: {chat.title} ({chat.id})")
        record_user_interaction(sender, chat)
    except Exception as e:
        logger.error(f"❌ Error in groupinfo: {e}")
        await message.reply_text(f"❌ Error getting group info: {str(e)[:100]}")


@app.on_message(filters.command("topics") & filters.group)
async def handle_topics(client: Client, message: Message):
    """List all topics in the current forum group (group admin only)"""
    try:
        sender = message.from_user
        if not sender:
            await message.reply_text("❌ Unable to verify user identity")
            return
        
        # Check if user is admin
        is_admin_check = await _is_chat_admin(client, message.chat.id, sender.id)
        if not is_admin_check:
            await message.reply_text("❌ Only group admins can use /topics")
            return
        
        try:
            topics_text = f"📋 **Topics in {message.chat.title}:**\n\n"
            topic_count = 0
            
            # Try modern Pyrogram get_forum_topics
            try:
                async for topic in client.get_forum_topics(message.chat.id):
                    topic_count += 1
                    topic_id = getattr(topic, 'id', 'Unknown')
                    topic_title = getattr(topic, 'title', 'Unknown')
                    icon = getattr(topic, 'icon_emoji', '📁')
                    topics_text += f"{icon} **{topic_title}**\n   ID: `{topic_id}`\n   Usage: `topic_{topic_id}` or \"{topic_title}\"\n\n"
            except Exception as e:
                logger.debug(f"Could not get forum topics: {e}")
                # Fallback to manual mappings
                topics_text = "❌ Automatic topic detection not available.\n\n"
                topics_text += "**🔧 Manual Topic Setup:**\n"
                topics_text += "Use `/addtopic \"Topic Name\" topic_id` to add topics manually.\n\n"
                topics_text += "**Your manual topics:**\n"
                
                # Show manual mappings
                topics = load_topics()
                chat_id_str = str(message.chat.id)
                if chat_id_str in topics and topics[chat_id_str]:
                    for topic_name, topic_id in topics[chat_id_str].items():
                        topics_text += f"📁 **{topic_name.title()}**\n   ID: `{topic_id}`\n   Usage: `\"{topic_name.title()}\"`\n\n"
                else:
                    topics_text += "No manual topics added yet.\n\n"
                
                topics_text += "**How to find topic_id:**\n"
                topics_text += "1. Click on a topic in Telegram\n"
                topics_text += "2. Look at the URL: `t=123` (topic_id is 123)\n"
                topics_text += "3. Or try common numbers: 2, 3, 4, 5...\n\n"
                topics_text += "**Example:**\n"
                topics_text += "`/addtopic \"General\" 2`\n"
                topics_text += "`/send_photo 1 \"General\"`"
            
            if topic_count == 0 and "Automatic topic detection" not in topics_text:
                topics_text = "📭 This group has no topics (not a forum group)"
            elif topic_count > 0:
                topics_text += f"**Total: {topic_count} topics**\n\n"
                topics_text += "**Usage examples:**\n"
                topics_text += f"`/send_photo 1 topic_{topic_id}`\n"
                topics_text += f"`/send_video 1 \"{topic_title}\"`\n"
            
            await message.reply_text(topics_text)
            logger.info(f"✅ TOPICS: Listed {topic_count} topics for {message.chat.title}")
            
        except Exception as e:
            if "CHAT_ADMIN_REQUIRED" in str(e) or "FORUM_TOPIC_REQUIRED" in str(e):
                await message.reply_text("❌ This group doesn't have topics or bot needs admin permissions")
            else:
                await message.reply_text(f"❌ Error getting topics: {str(e)[:100]}")
            logger.error(f"❌ Topics error: {e}")
            
    except Exception as e:
        logger.error(f"❌ Error in topics: {e}")
        await message.reply_text(f"❌ Error: {str(e)[:100]}")


@app.on_message(filters.command("topics") & filters.private)
async def handle_topics_private(client: Client, message: Message):
    """List topics for a managed group by index or ID in private chat. Usage: /topics <index_or_id>"""
    try:
        if not is_admin(message.from_user.id):
            await message.reply_text("❌ Admin only")
            return

        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            await message.reply_text("📝 Usage: /topics <index_or_id>\nUse /listgroups to see group indices")
            return

        target_str = args[1]
        group_id, group_id_str, is_index = _get_group_id_from_index(target_str)
        normalized_gid = _normalize_group_id(group_id_str)

        groups = load_managed_groups()
        if group_id_str not in groups and str(normalized_gid) not in groups:
            await message.reply_text(f"❌ Group {target_str} not found in managed groups\nUse /listgroups to see available groups")
            return

        try:
            topics_text = f"📋 **Topics in {groups.get(str(normalized_gid), groups.get(group_id_str,{})).get('name','Group')}**\n\n"
            topic_count = 0
            # Try modern Pyrogram get_forum_topics
            try:
                async for topic in client.get_forum_topics(normalized_gid):
                    topic_count += 1
                    topic_id = getattr(topic, 'id', 'Unknown')
                    topic_title = getattr(topic, 'title', 'Unknown')
                    icon = getattr(topic, 'icon_emoji', '📁')
                    topics_text += f"{icon} **{topic_title}**\n   ID: `{topic_id}`\n   Usage: `topic_{topic_id}` or \"{topic_title}\"\n\n"
            except Exception as e:
                logger.debug(f"Could not get forum topics: {e}")
                topics_text = "❌ Automatic topic detection not available.\n\n"
                topics_text += "**🔧 Manual Topic Setup:**\nUse `/addtopic \"Topic Name\" topic_id` to add topics manually.\n\n"
                topics = load_topics()
                chat_id_str = str(normalized_gid)
                if chat_id_str in topics and topics[chat_id_str]:
                    for topic_name, topic_id in topics[chat_id_str].items():
                        topics_text += f"📁 **{topic_name.title()}**\n   ID: `{topic_id}`\n   Usage: `\"{topic_name.title()}\"`\n\n"
                else:
                    topics_text += "No manual topics added yet.\n\n"

            if topic_count == 0 and "Automatic topic detection" not in topics_text:
                topics_text = "📭 This group has no topics (not a forum group)"
            elif topic_count > 0:
                topics_text += f"**Total: {topic_count} topics**\n\n"

            await message.reply_text(topics_text)
        except Exception as e:
            await message.reply_text(f"❌ Error getting topics for group {target_str}: {str(e)[:100]}")
            logger.error(f"❌ Topics error (private): {e}")
    except Exception as e:
        logger.error(f"❌ Error in handle_topics_private: {e}")
        await message.reply_text(f"❌ Error: {str(e)[:100]}")


@app.on_message(filters.command("addtopic") & filters.group)
async def handle_addtopic(client: Client, message: Message):
    """Add a manual topic mapping (group admin only). Usage: /addtopic "Topic Name" topic_id"""
    try:
        sender = message.from_user
        if not sender:
            await message.reply_text("❌ Unable to verify user identity")
            return
        
        # Check if user is admin
        is_admin_check = await _is_chat_admin(client, message.chat.id, sender.id)
        if not is_admin_check:
            await message.reply_text("❌ Only group admins can use /addtopic")
            return
        
        # Parse command: /addtopic "Topic Name" topic_id
        args = message.text.split(maxsplit=2)
        if len(args) < 3:
            await message.reply_text(
                "❌ Usage: /addtopic \"Topic Name\" topic_id\n\n"
                "**Example:**\n"
                "/addtopic \"General\" 2\n"
                "/addtopic \"Music\" 3\n\n"
                "**How to find topic_id:**\n"
                "1. Click on the topic in Telegram\n"
                "2. Look at the URL - the number after 't=' is the topic_id\n"
                "3. Or try numbers starting from 2, 3, 4..."
            )
            return
        
        topic_name = args[1].strip('"\'')
        try:
            topic_id = int(args[2])
        except ValueError:
            await message.reply_text("❌ topic_id must be a number")
            return
        
        # Add the mapping
        add_topic_mapping(message.chat.id, topic_name, topic_id)
        
        await message.reply_text(
            f"✅ Added topic mapping:\n"
            f"**Name:** {topic_name}\n"
            f"**ID:** {topic_id}\n\n"
            f"Now you can use:\n"
            f"`/send_photo [group] \"{topic_name}\"`\n"
            f"`/send_video [group] \"{topic_name}\"`\n"
            f"`/send_document [group] \"{topic_name}\"`\n\n"
            f"Replace [group] with your group number or ID"
        )
        logger.info(f"✅ ADDTOPIC: {sender.id} added mapping '{topic_name}' -> {topic_id} in {message.chat.title}")
        
    except Exception as e:
        logger.error(f"❌ Error in addtopic: {e}")
        await message.reply_text(f"❌ Error: {str(e)[:100]}")


@app.on_message(filters.command("status") & (filters.private | filters.group))
async def handle_status(client: Client, message: Message):
    """For normal users: show which managed groups they are in and if they are muted/banned/kicked.
    Usage: /status (private) or /status in group (checks in that group)."""
    try:
        user = message.from_user
        record_user_interaction(user, message.chat)

        groups = load_managed_groups()
        if not groups:
            await message.reply_text("📭 No managed groups available")
            return

        # If run in a group, only check that group for privacy
        if message.chat.type != 'private':
            try:
                member = await client.get_chat_member(message.chat.id, user.id)
                status = getattr(member, 'status', 'unknown')
                # Map status to readable state
                if status == 'restricted':
                    perms = getattr(member, 'privileges', None) or getattr(member, 'permissions', None)
                    can_send = None
                    try:
                        if perms and hasattr(perms, 'can_send_messages'):
                            can_send = getattr(perms, 'can_send_messages', None)
                        elif perms and isinstance(perms, dict):
                            can_send = perms.get('can_send_messages')
                    except Exception:
                        can_send = None
                    if can_send is False:
                        state = '🔇 Muted in this chat'
                    else:
                        state = '⚠️ Restricted in this chat'
                elif status == 'kicked':
                    state = '🚫 Banned from this chat'
                elif status == 'left':
                    state = '👋 You left this chat'
                elif status in ('administrator', 'creator'):
                    state = f"⭐ {status.capitalize()} in this chat"
                elif status == 'member':
                    state = '✅ Member of this chat'
                else:
                    state = status
                await message.reply_text(f"Your status: {state}")
            except Exception:
                await message.reply_text("Could not fetch your status in this chat")
            return

        # Private: show summary across managed groups (limit to first 20 to avoid rate limits)
        keys = list(groups.keys())[:20]
        report = f"📊 **Your status across {len(groups)} managed groups (first {len(keys)})**\n\n"
        for gid in keys:
            state = 'unknown'
            try:
                member = await client.get_chat_member(int(gid), user.id)
                status = getattr(member, 'status', 'unknown')
                if status == 'restricted':
                    # Check if user can send messages
                    perms = getattr(member, 'privileges', None) or getattr(member, 'permissions', None)
                    can_send = None
                    try:
                        if perms and hasattr(perms, 'can_send_messages'):
                            can_send = getattr(perms, 'can_send_messages', None)
                        elif perms and isinstance(perms, dict):
                            can_send = perms.get('can_send_messages')
                    except Exception:
                        can_send = None
                    if can_send is False:
                        state = '🔇 Muted'
                    else:
                        state = '⚠️ Restricted'
                elif status == 'kicked':
                    state = '🚫 Banned'
                elif status == 'left':
                    state = '👋 Left/Not member'
                elif status in ('administrator', 'creator'):
                    state = f"⭐ {status.capitalize()}"
                elif status == 'member':
                    state = '✅ Member'
                else:
                    state = status
            except Exception:
                state = '❓ Unknown'
            gname = groups[gid].get('name')
            report += f"• {gname}: {state}\n"

        if len(groups) > len(keys):
            report += "\n(Results limited; contact admin for a full report)"

        await message.reply_text(report)
    except Exception as e:
        logger.error(f"❌ Error in status: {e}")
        await message.reply_text("❌ Error fetching status")

@app.on_message(filters.command("mute") & filters.group)
async def handle_mute(client: Client, message: Message):
    """Mute a user in the group"""
    try:
        # Check admin permission
        try:
            member = await client.get_chat_member(message.chat.id, message.from_user.id)
            if not member.privileges or (not member.privileges.can_restrict_members):
                await message.reply_text("❌ You need to be admin to use this command")
                return
        except:
            await message.reply_text("❌ You need admin privileges")
            return
        
        # Get user to mute
        if message.reply_to_message:
            user_id = message.reply_to_message.from_user.id
            user_name = message.reply_to_message.from_user.first_name
        else:
            await message.reply_text("❌ Reply to user's message to mute them")
            return
        
        # Mute the user
        await client.restrict_chat_member(
            message.chat.id,
            user_id,
            ChatPermissions(can_send_messages=False)
        )
        await message.reply_text(f"🔇 Muted {user_name}")
        logger.info(f"✅ MUTE: {user_name} ({user_id}) in {message.chat.title}")
        record_user_interaction(message.from_user, message.chat)
    except ChatAdminRequired:
        await message.reply_text("❌ Bot needs admin permissions")
    except Exception as e:
        logger.error(f"❌ Error in mute: {e}")
        await message.reply_text("❌ Error muting user")

@app.on_message(filters.command("unmute") & filters.group)
async def handle_unmute(client: Client, message: Message):
    """Unmute a user in the group"""
    try:
        try:
            member = await client.get_chat_member(message.chat.id, message.from_user.id)
            if not member.privileges or (not member.privileges.can_restrict_members):
                await message.reply_text("❌ You need to be admin to use this command")
                return
        except:
            await message.reply_text("❌ You need admin privileges")
            return
        
        if message.reply_to_message:
            user_id = message.reply_to_message.from_user.id
            user_name = message.reply_to_message.from_user.first_name
        else:
            await message.reply_text("❌ Reply to user's message to unmute them")
            return
        
        await client.restrict_chat_member(
            message.chat.id,
            user_id,
            ChatPermissions(can_send_messages=True)
        )
        await message.reply_text(f"🔊 Unmuted {user_name}")
        logger.info(f"✅ UNMUTE: {user_name} ({user_id}) in {message.chat.title}")
        record_user_interaction(message.from_user, message.chat)
    except Exception as e:
        logger.error(f"❌ Error in unmute: {e}")
        await message.reply_text("❌ Error unmuting user")

@app.on_message(filters.command("kick") & filters.group)
async def handle_kick(client: Client, message: Message):
    """Kick a user from the group"""
    try:
        try:
            member = await client.get_chat_member(message.chat.id, message.from_user.id)
            if not member.privileges or (not member.privileges.can_restrict_members):
                await message.reply_text("❌ You need to be admin to use this command")
                return
        except:
            await message.reply_text("❌ You need admin privileges")
            return
        
        if message.reply_to_message:
            user_id = message.reply_to_message.from_user.id
            user_name = message.reply_to_message.from_user.first_name
        else:
            await message.reply_text("❌ Reply to user's message to kick them")
            return
        
        await client.ban_chat_member(message.chat.id, user_id)
        await message.reply_text(f"👢 Kicked {user_name}")
        logger.info(f"✅ KICK: {user_name} ({user_id}) from {message.chat.title}")
        record_user_interaction(message.from_user, message.chat)
    except ChatAdminRequired:
        await message.reply_text("❌ Bot needs admin permissions")
    except Exception as e:
        logger.error(f"❌ Error in kick: {e}")
        await message.reply_text("❌ Error kicking user")

@app.on_message(filters.command("ban") & filters.group)
async def handle_ban(client: Client, message: Message):
    """Ban a user from the group"""
    try:
        try:
            member = await client.get_chat_member(message.chat.id, message.from_user.id)
            if not member.privileges or (not member.privileges.can_restrict_members):
                await message.reply_text("❌ You need to be admin to use this command")
                return
        except:
            await message.reply_text("❌ You need admin privileges")
            return
        
        if message.reply_to_message:
            user_id = message.reply_to_message.from_user.id
            user_name = message.reply_to_message.from_user.first_name
        else:
            await message.reply_text("❌ Reply to user's message to ban them")
            return
        
        await client.ban_chat_member(message.chat.id, user_id)
        await message.reply_text(f"🚫 Banned {user_name}")
        logger.info(f"✅ BAN: {user_name} ({user_id}) from {message.chat.title}")
        record_user_interaction(message.from_user, message.chat)
    except ChatAdminRequired:
        await message.reply_text("❌ Bot needs admin permissions")
    except Exception as e:
        logger.error(f"❌ Error in ban: {e}")
        await message.reply_text("❌ Error banning user")


# ==================== Admin send / media commands ====================


@app.on_message(filters.command("say") & filters.private)
async def handle_say(client: Client, message: Message):
    """Send a text message to a group. Usage: /say <index_or_id> <text> [topic_name]
    Example: /say 1 Hello world
    With topic: /say 1 "General" Hello world"""
    try:
        sender = message.from_user
        if not is_admin(sender.id):
            await message.reply_text("❌ Admin only")
            return
        
        args = message.text.split(maxsplit=3)
        if len(args) < 3:
            await message.reply_text("📝 Usage: /say <index_or_id> <text> [topic_name]\n\nExample: /say 1 Hello world\nWith topic: /say 1 \"General\" Hello world\n\nUse /listgroups to see group indices")
            return
        
        target_str = args[1]
        text = args[2]
        topic_id = None
        
        # Check if third arg is topic_name (optional)
        if len(args) >= 4:
            potential_topic = args[2]
            text = args[3]
            # Check if it's a topic name (not starting with topic_ and not a small number)
            if not potential_topic.startswith('topic_') and (not potential_topic.isdigit() or len(potential_topic) > 3):
                # Try to resolve topic by name
                group_id, group_id_str, is_index = _get_group_id_from_index(target_str)
                normalized_gid = _normalize_group_id(group_id_str)
                topic_id = await _resolve_topic_id(client, int(normalized_gid), potential_topic)
                if not topic_id:
                    await message.reply_text(f"⚠️ Could not resolve topic '{potential_topic}'. Sending to general chat.")
            else:
                # It's probably a topic ID, not a name
                text = args[3]
        
        try:
            group_id, group_id_str, is_index = _get_group_id_from_index(target_str)
            normalized_gid = _normalize_group_id(group_id_str)
            await client.send_message(normalized_gid, text, reply_to_message_id=topic_id)
            group_idx = _get_group_index(group_id_str)
            idx_str = f"#{group_idx}" if group_idx > 0 else target_str
            topic_str = f" (topic {topic_id})" if topic_id else ""
            await message.reply_text(f"✅ Message sent to group {idx_str}{topic_str}")
            logger.info(f"✅ SAY: Admin {sender.id} -> {target_str} ({group_id_str}){topic_str}")
        except Exception as e:
            await message.reply_text(f"❌ Failed to send to group {target_str}: {str(e)[:100]}")
            logger.error(f"❌ Say error: {e}")
    except Exception as e:
        logger.error(f"❌ Error in say: {e}")
        await message.reply_text(f"❌ Error: {str(e)[:100]}")


async def _copy_media_to_target(client: Client, source_msg: Message, target_chat: str, topic_id: int = None):
    """Copy a media-containing message to a target chat (preserves file, avoids forward header).
    
    Args:
        client: Pyrogram client
        source_msg: Source message with media
        target_chat: Target chat ID
        topic_id: Optional topic ID for topic-based sending (for topic-enabled groups)
    """
    if not source_msg:
        raise ValueError("No source message to copy")
    # Determine message id
    source_msg_id = getattr(source_msg, 'id', None) or getattr(source_msg, 'message_id', None)
    if source_msg_id is None:
        logger.debug(f"Source message attributes: {dir(source_msg)}")
        raise ValueError("Source message has no message_id or id")

    logger.debug(f"Copying message {source_msg_id} from {getattr(getattr(source_msg,'chat',None),'id',None)} to {target_chat} (topic={topic_id})")

    try:
        # Prefer server-side copy (no re-upload). Try variants that different
        # Pyrogram versions may expect: `message_thread_id` or `reply_to_message_id`.
        if topic_id:
            try:
                await _attempt_copy_with_thread(client, target_chat, source_msg.chat.id, source_msg_id, topic_id)
                return
            except Exception as e:
                logger.warning(f"Copy to topic failed, falling back to download+upload: {e}")
                await _download_and_upload_to_topic(client, source_msg, target_chat, topic_id)
                return
        else:
            try:
                await client.copy_message(target_chat, source_msg.chat.id, source_msg_id)
                return
            except TypeError as e:
                # Some pyrogram versions may raise TypeError for unexpected args
                logger.warning(f"copy_message without thread failed: {e}. Trying forward_messages as fallback")
                await client.forward_messages(target_chat, source_msg.chat.id, source_msg_id)
                return
            except Exception as e:
                logger.warning(f"copy_message failed, falling back to download+upload: {e}")
                await _download_and_upload_to_topic(client, source_msg, target_chat, None)
                return
    except Exception as e:
        logger.error(f"Error in _copy_media_to_target: {e}")
        raise


async def _attempt_copy_with_thread(client: Client, target_chat: str, from_chat: int, message_id: int, thread_id: int) -> str:
    """Try to copy a message into a forum topic/thread using multiple possible parameter names.

    Returns a short string describing which method succeeded.
    Raises the last exception if all attempts fail.
    """
    last_exc = None
    # Try with message_thread_id first
    try:
        await client.copy_message(target_chat, from_chat, message_id, message_thread_id=thread_id)
        logger.info(f"Copied message into thread using copy_message(message_thread_id={thread_id})")
        return "copy_message(message_thread_id)"
    except TypeError as e:
        last_exc = e
        logger.debug(f"copy_message(message_thread_id=...) not supported: {e}")
    except Exception as e:
        last_exc = e
        logger.debug(f"copy_message with message_thread_id failed: {e}")

    # Try with reply_to_message_id (some pyrogram versions map this)
    try:
        await client.copy_message(target_chat, from_chat, message_id, reply_to_message_id=thread_id)
        logger.info(f"Copied message into thread using copy_message(reply_to_message_id={thread_id})")
        return "copy_message(reply_to_message_id)"
    except Exception as e:
        last_exc = e
        logger.debug(f"copy_message(reply_to_message_id=...) failed: {e}")

    # Do not attempt forward_messages with message_thread_id since some Pyrogram versions reject that kwarg.
    # If both copy attempts failed, raise the last exception to let the caller fall back to upload.
    raise last_exc


async def _download_and_upload_to_topic(client: Client, source_msg: Message, target_chat: str, topic_id: int):
    """Download media from source message and upload to target topic using reply_to_message_id"""
    import tempfile
    import os

    temp_file = None
    try:
        # Prefer streaming to a temp file to avoid large memory usage
        if source_msg.photo:
            temp_file = await client.download_media(source_msg.photo.file_id)
            await client.send_photo(target_chat, temp_file, caption=source_msg.caption, message_thread_id=topic_id)
        elif source_msg.video:
            temp_file = await client.download_media(source_msg.video.file_id)
            await client.send_video(target_chat, temp_file, caption=source_msg.caption, message_thread_id=topic_id)
        elif source_msg.document:
            temp_file = await client.download_media(source_msg.document.file_id)
            await client.send_document(target_chat, temp_file, caption=source_msg.caption, message_thread_id=topic_id)
        elif source_msg.audio:
            temp_file = await client.download_media(source_msg.audio.file_id)
            await client.send_audio(target_chat, temp_file, caption=source_msg.caption, message_thread_id=topic_id)
        elif source_msg.animation:
            temp_file = await client.download_media(source_msg.animation.file_id)
            await client.send_animation(target_chat, temp_file, caption=source_msg.caption, message_thread_id=topic_id)
        else:
            # Generic media download
            temp_file = await client.download_media(source_msg)
            await client.send_document(target_chat, temp_file, caption=source_msg.caption, message_thread_id=topic_id)

    except Exception as e:
        logger.error(f"Error in _download_and_upload_to_topic: {e}")
        raise
    finally:
        # Clean up temp file if created
        try:
            if temp_file and os.path.exists(temp_file):
                os.remove(temp_file)
        except Exception:
            pass


def _is_url(path: str) -> bool:
    return path.startswith("http://") or path.startswith("https://")


async def _send_media_by_path(client: Client, target, media_path: str, media_type: str = "photo", topic_id: int = None):
    """Send media by URL or local path to target chat.
    
    Args:
        client: Pyrogram client
        target: Target chat ID
        media_path: URL or local file path
        media_type: Type of media (photo, video, document)
        topic_id: Optional topic ID for topic-based sending (for topic-enabled groups)
    """
    if _is_url(media_path):
        if media_type == "photo":
            await client.send_photo(target, media_path, message_thread_id=topic_id)
        elif media_type == "video":
            await client.send_video(target, media_path, message_thread_id=topic_id)
        else:
            await client.send_document(target, media_path, message_thread_id=topic_id)
    else:
        # assume local file path
        if media_type == "photo":
            await client.send_photo(target, media_path, message_thread_id=topic_id)
        elif media_type == "video":
            await client.send_video(target, media_path, message_thread_id=topic_id)
        else:
            await client.send_document(target, media_path, message_thread_id=topic_id)


@app.on_message(filters.command("send_photo") & filters.group)
async def handle_send_photo_group(client: Client, message: Message):
    """Copy a photo to the current group (group admin only). Usage: /send_photo (reply to photo)"""
    try:
        sender = message.from_user
        if not sender:
            await message.reply_text("❌ Unable to verify user identity")
            return
        
        # Check if user is group admin
        is_admin_check = False
        try:
            is_admin_check = await _is_chat_admin(client, message.chat.id, sender.id)
        except Exception as e:
            logger.error(f"❌ Admin check failed for send_photo_group: {e}")
            try:
                member = await client.get_chat_member(message.chat.id, sender.id)
                status = getattr(member, 'status', None)
                is_admin_check = status in ('administrator', 'creator')
            except Exception:
                is_admin_check = False
        
        if not is_admin_check:
            await message.reply_text("❌ You need to be group admin to use this command")
            return
        
        # Check if replying to a photo
        if not message.reply_to_message or not message.reply_to_message.photo:
            await message.reply_text("❌ Reply to a photo to copy it to this group")
            return
        
        try:
            # Copy the photo to the same group (removes forward header)
            reply_msg_id = getattr(message.reply_to_message, 'message_id', None)
            if reply_msg_id:
                await client.copy_message(
                    message.chat.id,
                    message.reply_to_message.chat.id,
                    reply_msg_id
                )
                await message.reply_text("✅ Photo copied to this group")
                logger.info(f"✅ SEND_PHOTO_GROUP: Admin {sender.id} copied photo to {message.chat.title}")
            else:
                await message.reply_text("❌ Unable to get message ID from replied message")
                return
            record_user_interaction(sender, message.chat)
        except Exception as e:
            await message.reply_text(f"❌ Failed to copy photo: {str(e)[:100]}")
            logger.error(f"❌ Send photo group error: {e}")
            
    except Exception as e:
        logger.error(f"❌ Error in send_photo_group: {e}")
        await message.reply_text(f"❌ Error: {str(e)[:100]}")


@app.on_message(filters.command("send_photo") & filters.private)
async def handle_send_photo(client: Client, message: Message):
    """Send a photo to a group. Usage: /send_photo <index_or_id> [topic_id]
    
    Can be used in 3 ways:
    1. Reply to photo: /send_photo 1
    2. Attach photo: /send_photo 1 (with photo attached to command)
    3. With topic: /send_photo 1 topic_5 (for groups with topics)
    """
    try:
        sender = message.from_user
        if not is_admin(sender.id):
            await message.reply_text("❌ Admin only")
            return
        
        # Get the command text - could be None for media-only messages
        cmd_text = message.text or ""
        args = cmd_text.split(maxsplit=2) if cmd_text else []
        
        if len(args) < 2:
            await message.reply_text("📸 Usage: /send_photo <index> [topic_id/topic_name]\n\n"
                                    "**Ways to use:**\n"
                                    "1️⃣ Reply to photo:\n   /send_photo 1\n\n"
                                    "2️⃣ Attach photo:\n   /send_photo 1 (with photo)\n\n"
                                    "3️⃣ Send to topic:\n   /send_photo 1 topic_5\n   /send_photo 1 \"General Discussion\"\n\n"
                                    "Use /listgroups to see group indices")
            return
        
        target_str = args[1]
        topic_id_str = args[2] if len(args) >= 3 else None
        
        # First validate and get group info
        group_id, group_id_str, is_index = _get_group_id_from_index(target_str)
        normalized_gid = _normalize_group_id(group_id_str)
        
        # Validate that the group exists in managed groups
        groups = load_managed_groups()
        # Check both original group_id_str and normalized_gid
        if group_id_str not in groups and str(normalized_gid) not in groups:
            await message.reply_text(f"❌ Group {target_str} not found in managed groups\nUse /listgroups to see available groups")
            return
        
        # Extract topic ID if provided (format: topic_123, 123, or topic name)
        topic_id = None
        if topic_id_str:
            logger.info(f"Resolving topic '{topic_id_str}' for group {normalized_gid}")
            topic_id = await _resolve_topic_id(client, normalized_gid, topic_id_str)
            if topic_id:
                logger.info(f"Topic ID resolved: {topic_id}")
            else:
                logger.warning(f"Could not resolve topic: {topic_id_str}")
                await message.reply_text(f"⚠️ Could not resolve topic '{topic_id_str}'. Sending to general chat instead.")
        else:
            logger.info(f"No topic specified, sending to general chat")
        
        # Case 1: Reply to photo
        if message.reply_to_message and message.reply_to_message.photo:
            try:
                await _copy_media_to_target(client, message.reply_to_message, normalized_gid, topic_id)
                group_idx = _get_group_index(group_id_str)
                idx_str = f"#{group_idx}" if group_idx > 0 else target_str
                topic_str = f" (topic {topic_id})" if topic_id else ""
                await message.reply_text(f"✅ Photo sent to group {idx_str}{topic_str}")
                logger.info(f"✅ SEND_PHOTO (reply): Admin {sender.id} -> {target_str}{topic_str}")
                return
            except Exception as e:
                await message.reply_text(f"❌ Failed to send photo: {str(e)[:100]}")
                logger.error(f"❌ Send photo error: {e}")
                return
        
        # Case 2: Photo attached to command message
        if message.photo:
            try:
                if topic_id:
                    method = await _attempt_copy_with_thread(client, normalized_gid, message.chat.id, getattr(message, 'message_id', None), topic_id)
                else:
                    await client.copy_message(
                        normalized_gid,
                        message.chat.id,
                        getattr(message, 'message_id', None)
                    )
                    method = 'copy_message'
                group_idx = _get_group_index(group_id_str)
                idx_str = f"#{group_idx}" if group_idx > 0 else target_str
                topic_str = f" (topic {topic_id})" if topic_id else ""
                await message.reply_text(f"✅ Photo sent to group {idx_str}{topic_str} (method: {method})")
                logger.info(f"✅ SEND_PHOTO (attached): Admin {sender.id} -> {target_str}{topic_str} (method: {method})")
                return
            except Exception as e:
                await message.reply_text(f"❌ Failed to send photo: {str(e)[:100]}")
                logger.error(f"❌ Send photo error: {e}")
                return
        
        # Case 3: URL or path provided
        args2 = (cmd_text or "").split(maxsplit=2)
        if len(args2) >= 3:
            path_arg = args2[2]
            # Only treat as URL/path if it doesn't look like a topic ID
            if not (path_arg.startswith('topic_') or (path_arg.isdigit() and len(path_arg) < 4)):
                try:
                    await _send_media_by_path(client, normalized_gid, path_arg, media_type="photo", topic_id=topic_id)
                    group_idx = _get_group_index(group_id_str)
                    idx_str = f"#{group_idx}" if group_idx > 0 else target_str
                    await message.reply_text(f"✅ Photo sent to group {idx_str}")
                    logger.info(f"✅ SEND_PHOTO (url): Admin {sender.id} -> {target_str}")
                except Exception as e:
                    await message.reply_text(f"❌ Failed to send photo: {str(e)[:100]}")
                    logger.error(f"❌ Send photo error: {e}")
            else:
                await message.reply_text("❌ Reply to a photo, attach one, or provide URL")
        else:
            await message.reply_text("❌ Reply to a photo, attach one, or provide URL")
    except Exception as e:
        logger.error(f"❌ Error in send_photo: {e}")
        await message.reply_text(f"❌ Error sending photo: {str(e)[:100]}")


@app.on_message(filters.command("send_video") & filters.group)
async def handle_send_video_group(client: Client, message: Message):
    """Copy a video to the current group (group admin only). Usage: /send_video (reply to video)"""
    try:
        sender = message.from_user
        if not sender:
            await message.reply_text("❌ Unable to verify user identity")
            return
        
        # Check if user is group admin
        is_admin_check = False
        try:
            is_admin_check = await _is_chat_admin(client, message.chat.id, sender.id)
        except Exception as e:
            logger.error(f"❌ Admin check failed for send_video_group: {e}")
            try:
                member = await client.get_chat_member(message.chat.id, sender.id)
                status = getattr(member, 'status', None)
                is_admin_check = status in ('administrator', 'creator')
            except Exception:
                is_admin_check = False
        
        if not is_admin_check:
            await message.reply_text("❌ You need to be group admin to use this command")
            return
        
        # Check if replying to a video
        if not message.reply_to_message or not message.reply_to_message.video:
            await message.reply_text("❌ Reply to a video to copy it to this group")
            return
        
        try:
            # Copy the video to the same group (removes forward header)
            reply_msg_id = getattr(message.reply_to_message, 'message_id', None)
            if reply_msg_id:
                await client.copy_message(
                    message.chat.id,
                    message.reply_to_message.chat.id,
                    reply_msg_id
                )
                await message.reply_text("✅ Video copied to this group")
                logger.info(f"✅ SEND_VIDEO_GROUP: Admin {sender.id} copied video to {message.chat.title}")
            else:
                await message.reply_text("❌ Unable to get message ID from replied message")
                return
            record_user_interaction(sender, message.chat)
        except Exception as e:
            await message.reply_text(f"❌ Failed to copy video: {str(e)[:100]}")
            logger.error(f"❌ Send video group error: {e}")
            
    except Exception as e:
        logger.error(f"❌ Error in send_video_group: {e}")
        await message.reply_text(f"❌ Error: {str(e)[:100]}")


@app.on_message(filters.command("send_video") & filters.private)
async def handle_send_video(client: Client, message: Message):
    """Send a video to a group. Usage: /send_video <index_or_id> [topic_id]
    
    Can be used in 3 ways:
    1. Reply to video: /send_video 1
    2. Attach video: /send_video 1 (with video attached to command)
    3. With topic: /send_video 1 topic_5 (for groups with topics)
    """
    try:
        sender = message.from_user
        if not is_admin(sender.id):
            await message.reply_text("❌ Admin only")
            return
        
        cmd_text = message.text or ""
        args = cmd_text.split(maxsplit=2) if cmd_text else []
        if len(args) < 2:
            await message.reply_text("🎥 Usage: /send_video <index> [topic_id/topic_name]\n\n"
                                    "**Ways to use:**\n"
                                    "1️⃣ Reply to video:\n   /send_video 1\n\n"
                                    "2️⃣ Attach video:\n   /send_video 1 (with video)\n\n"
                                    "3️⃣ Send to topic:\n   /send_video 1 topic_5\n   /send_video 1 \"General Discussion\"\n\n"
                                    "Use /listgroups to see group indices")
            return
        
        target_str = args[1]
        topic_id_str = args[2] if len(args) >= 3 else None
        
        # First validate and get group info
        group_id, group_id_str, is_index = _get_group_id_from_index(target_str)
        normalized_gid = _normalize_group_id(group_id_str)
        
        # Validate that the group exists in managed groups
        groups = load_managed_groups()
        # Check both original group_id_str and normalized_gid
        if group_id_str not in groups and str(normalized_gid) not in groups:
            await message.reply_text(f"❌ Group {target_str} not found in managed groups\nUse /listgroups to see available groups")
            return
        
        # Extract topic ID if provided (format: topic_123, 123, or topic name)
        topic_id = None
        if topic_id_str:
            logger.info(f"Resolving topic '{topic_id_str}' for group {normalized_gid}")
            topic_id = await _resolve_topic_id(client, normalized_gid, topic_id_str)
            if topic_id:
                logger.info(f"Topic ID resolved: {topic_id}")
            else:
                logger.warning(f"Could not resolve topic: {topic_id_str}")
                await message.reply_text(f"⚠️ Could not resolve topic '{topic_id_str}'. Sending to general chat instead.")
        else:
            logger.info(f"No topic specified, sending to general chat")
        
        # Case 1: Reply to video
        if message.reply_to_message and message.reply_to_message.video:
            try:
                await _copy_media_to_target(client, message.reply_to_message, normalized_gid, topic_id)
                group_idx = _get_group_index(group_id_str)
                idx_str = f"#{group_idx}" if group_idx > 0 else target_str
                topic_str = f" (topic {topic_id})" if topic_id else ""
                await message.reply_text(f"✅ Video sent to group {idx_str}{topic_str}")
                logger.info(f"✅ SEND_VIDEO (reply): Admin {sender.id} -> {target_str}{topic_str}")
                return
            except Exception as e:
                await message.reply_text(f"❌ Failed to send video: {str(e)[:100]}")
                logger.error(f"❌ Send video error: {e}")
                return
        
        # Case 2: Video attached to command message
        if message.video:
            try:
                if topic_id:
                    method = await _attempt_copy_with_thread(client, normalized_gid, message.chat.id, getattr(message, 'message_id', None), topic_id)
                else:
                    await client.copy_message(
                        normalized_gid,
                        message.chat.id,
                        getattr(message, 'message_id', None)
                    )
                    method = 'copy_message'
                group_idx = _get_group_index(group_id_str)
                idx_str = f"#{group_idx}" if group_idx > 0 else target_str
                topic_str = f" (topic {topic_id})" if topic_id else ""
                await message.reply_text(f"✅ Video sent to group {idx_str}{topic_str} (method: {method})")
                logger.info(f"✅ SEND_VIDEO (attached): Admin {sender.id} -> {target_str}{topic_str} (method: {method})")
                return
            except Exception as e:
                await message.reply_text(f"❌ Failed to send video: {str(e)[:100]}")
                logger.error(f"❌ Send video error: {e}")
                return
        
        # Case 3: URL or path provided
        args2 = (cmd_text or "").split(maxsplit=2)
        if len(args2) >= 3:
            path_arg = args2[2]
            # Only treat as URL/path if it doesn't look like a topic ID
            if not (path_arg.startswith('topic_') or (path_arg.isdigit() and len(path_arg) < 4)):
                try:
                    await _send_media_by_path(client, normalized_gid, path_arg, media_type="video", topic_id=topic_id)
                    group_idx = _get_group_index(group_id_str)
                    idx_str = f"#{group_idx}" if group_idx > 0 else target_str
                    await message.reply_text(f"✅ Video sent to group {idx_str}")
                    logger.info(f"✅ SEND_VIDEO (url): Admin {sender.id} -> {target_str}")
                except Exception as e:
                    await message.reply_text(f"❌ Failed to send video: {str(e)[:100]}")
                    logger.error(f"❌ Send video error: {e}")
            else:
                await message.reply_text("❌ Reply to a video, attach one, or provide URL")
        else:
            await message.reply_text("❌ Reply to a video, attach one, or provide URL")
    except Exception as e:
        logger.error(f"❌ Error in send_video: {e}")
        await message.reply_text(f"❌ Error sending video: {str(e)[:100]}")


@app.on_message(filters.command("send_document") & filters.group)
async def handle_send_document_group(client: Client, message: Message):
    """Copy a document to the current group (group admin only). Usage: /send_document (reply to document)"""
    try:
        sender = message.from_user
        if not sender:
            await message.reply_text("❌ Unable to verify user identity")
            return
        
        # Check if user is group admin
        is_admin_check = False
        try:
            is_admin_check = await _is_chat_admin(client, message.chat.id, sender.id)
        except Exception as e:
            logger.error(f"❌ Admin check failed for send_document_group: {e}")
            try:
                member = await client.get_chat_member(message.chat.id, sender.id)
                status = getattr(member, 'status', None)
                is_admin_check = status in ('administrator', 'creator')
            except Exception:
                is_admin_check = False
        
        if not is_admin_check:
            await message.reply_text("❌ You need to be group admin to use this command")
            return
        
        # Check if replying to a document
        if not message.reply_to_message or not message.reply_to_message.document:
            await message.reply_text("❌ Reply to a document to copy it to this group")
            return
        
        try:
            # Copy the document to the same group (removes forward header)
            reply_msg_id = getattr(message.reply_to_message, 'message_id', None)
            if reply_msg_id:
                await client.copy_message(
                    message.chat.id,
                    message.reply_to_message.chat.id,
                    reply_msg_id
                )
                await message.reply_text("✅ Document copied to this group")
                logger.info(f"✅ SEND_DOCUMENT_GROUP: Admin {sender.id} copied document to {message.chat.title}")
            else:
                await message.reply_text("❌ Unable to get message ID from replied message")
                return
            record_user_interaction(sender, message.chat)
        except Exception as e:
            await message.reply_text(f"❌ Failed to copy document: {str(e)[:100]}")
            logger.error(f"❌ Send document group error: {e}")
            
    except Exception as e:
        logger.error(f"❌ Error in send_document_group: {e}")
        await message.reply_text(f"❌ Error: {str(e)[:100]}")


@app.on_message(filters.command("send_document") & filters.private)
async def handle_send_document(client: Client, message: Message):
    """Send a document to a group. Usage: /send_document <index_or_id> [topic_id]
    
    Can be used in 3 ways:
    1. Reply to document: /send_document 1
    2. Attach document: /send_document 1 (with document attached to command)
    3. With topic: /send_document 1 topic_5 (for groups with topics)
    """
    try:
        sender = message.from_user
        if not is_admin(sender.id):
            await message.reply_text("❌ Admin only")
            return
        
        cmd_text = message.text or ""
        args = cmd_text.split(maxsplit=2) if cmd_text else []
        if len(args) < 2:
            await message.reply_text("📝 Usage: /send_document <index> [topic_id/topic_name]\n\n"
                                    "**Ways to use:**\n"
                                    "1️⃣ Reply to document:\n   /send_document 1\n\n"
                                    "2️⃣ Attach document:\n   /send_document 1 (with document)\n\n"
                                    "3️⃣ Send to topic:\n   /send_document 1 topic_5\n   /send_document 1 \"General Discussion\"\n\n"
                                    "Use /listgroups to see group indices")
            return
        
        target_str = args[1]
        topic_id_str = args[2] if len(args) >= 3 else None
        
        # First validate and get group info
        group_id, group_id_str, is_index = _get_group_id_from_index(target_str)
        normalized_gid = _normalize_group_id(group_id_str)
        
        # Validate that the group exists in managed groups
        groups = load_managed_groups()
        # Check both original group_id_str and normalized_gid
        if group_id_str not in groups and str(normalized_gid) not in groups:
            await message.reply_text(f"❌ Group {target_str} not found in managed groups\nUse /listgroups to see available groups")
            return
        
        # Extract topic ID if provided (format: topic_123, 123, or topic name)
        topic_id = None
        if topic_id_str:
            logger.info(f"Resolving topic '{topic_id_str}' for group {normalized_gid}")
            topic_id = await _resolve_topic_id(client, normalized_gid, topic_id_str)
            if topic_id:
                logger.info(f"Topic ID resolved: {topic_id}")
            else:
                logger.warning(f"Could not resolve topic: {topic_id_str}")
                await message.reply_text(f"⚠️ Could not resolve topic '{topic_id_str}'. Sending to general chat instead.")
        else:
            logger.info(f"No topic specified, sending to general chat")
        
        # Case 1: Reply to document
        if message.reply_to_message and message.reply_to_message.document:
            try:
                await _copy_media_to_target(client, message.reply_to_message, normalized_gid, topic_id)
                group_idx = _get_group_index(group_id_str)
                idx_str = f"#{group_idx}" if group_idx > 0 else target_str
                topic_str = f" (topic {topic_id})" if topic_id else ""
                await message.reply_text(f"✅ Document sent to group {idx_str}{topic_str}")
                logger.info(f"✅ SEND_DOCUMENT (reply): Admin {sender.id} -> {target_str}{topic_str}")
                return
            except Exception as e:
                await message.reply_text(f"❌ Failed to send document: {str(e)[:100]}")
                logger.error(f"❌ Send document error: {e}")
                return
        
        # Case 2: Document attached to command message
        if message.document:
            try:
                if topic_id:
                    method = await _attempt_copy_with_thread(client, normalized_gid, message.chat.id, getattr(message, 'message_id', None), topic_id)
                else:
                    await client.copy_message(
                        normalized_gid,
                        message.chat.id,
                        getattr(message, 'message_id', None)
                    )
                    method = 'copy_message'
                group_idx = _get_group_index(group_id_str)
                idx_str = f"#{group_idx}" if group_idx > 0 else target_str
                topic_str = f" (topic {topic_id})" if topic_id else ""
                await message.reply_text(f"✅ Document sent to group {idx_str}{topic_str} (method: {method})")
                logger.info(f"✅ SEND_DOCUMENT (attached): Admin {sender.id} -> {target_str}{topic_str} (method: {method})")
                return
            except Exception as e:
                await message.reply_text(f"❌ Failed to send document: {str(e)[:100]}")
                logger.error(f"❌ Send document error: {e}")
                return
        
        # Case 3: URL or path provided
        args2 = (cmd_text or "").split(maxsplit=2)
        if len(args2) >= 3:
            path_arg = args2[2]
            # Only treat as URL/path if it doesn't look like a topic ID
            if not (path_arg.startswith('topic_') or (path_arg.isdigit() and len(path_arg) < 4)):
                try:
                    await _send_media_by_path(client, normalized_gid, path_arg, media_type="document", topic_id=topic_id)
                    group_idx = _get_group_index(group_id_str)
                    idx_str = f"#{group_idx}" if group_idx > 0 else target_str
                    await message.reply_text(f"✅ Document sent to group {idx_str}")
                    logger.info(f"✅ SEND_DOCUMENT (url): Admin {sender.id} -> {target_str}")
                except Exception as e:
                    await message.reply_text(f"❌ Failed to send document: {str(e)[:100]}")
                    logger.error(f"❌ Send document error: {e}")
            else:
                await message.reply_text("❌ Reply to a document, attach one, or provide URL")
        else:
            await message.reply_text("❌ Reply to a document, attach one, or provide URL")
    except Exception as e:
        logger.error(f"❌ Error in send_document: {e}")
        await message.reply_text(f"❌ Error sending document: {str(e)[:100]}")


@app.on_message(filters.command("forward") & filters.group)
async def handle_forward_group(client: Client, message: Message):
    """Forward or copy a replied message to a managed group. Usage: /forward <index_or_id> [topic]
    Reply to the message you want to forward in the source group, then run this command."""
    try:
        sender = message.from_user
        if not sender:
            await message.reply_text("❌ Unable to verify user identity")
            return

        # require admin in source group
        is_admin_check = await _is_chat_admin(client, message.chat.id, sender.id)
        if not is_admin_check:
            await message.reply_text("❌ You need to be group admin to use this command")
            return

        if not message.reply_to_message:
            await message.reply_text("❌ Reply to the message you want to forward")
            return

        args = message.text.split(maxsplit=2)
        if len(args) < 2:
            await message.reply_text("📝 Usage: /forward <index_or_id> [topic]")
            return

        target_str = args[1]
        topic_id_str = args[2] if len(args) >= 3 else None

        group_id, group_id_str, is_index = _get_group_id_from_index(target_str)
        normalized_gid = _normalize_group_id(group_id_str)

        groups = load_managed_groups()
        if group_id_str not in groups and str(normalized_gid) not in groups:
            await message.reply_text(f"❌ Group {target_str} not found in managed groups\nUse /listgroups to see available groups")
            return

        topic_id = None
        if topic_id_str:
            topic_id = await _resolve_topic_id(client, normalized_gid, topic_id_str)
            if not topic_id:
                await message.reply_text(f"⚠️ Could not resolve topic '{topic_id_str}'. Forwarding to general chat.")

        # Perform forwarding or copying depending on whether a topic is targeted
        src_msg = message.reply_to_message
        src_msg_id = getattr(src_msg, 'message_id', None)
        try:
            if topic_id:
                method = await _attempt_copy_with_thread(client, normalized_gid, src_msg.chat.id, src_msg_id, topic_id)
            else:
                # try forward (fast) — server-side forward
                await client.forward_messages(normalized_gid, src_msg.chat.id, src_msg_id)
                method = 'forward_messages'

            group_idx = _get_group_index(group_id_str)
            idx_str = f"#{group_idx}" if group_idx > 0 else target_str
            topic_str = f" (topic {topic_id})" if topic_id else ""
            await message.reply_text(f"✅ Message forwarded to group {idx_str}{topic_str} (method: {method})")
            logger.info(f"✅ FORWARD: Admin {sender.id} -> {target_str}{topic_str} (method: {method})")
            record_user_interaction(sender, message.chat)
        except Exception as e:
            logger.error(f"❌ Forward error: {e}")
            # Try copy fallback
            try:
                await _copy_media_to_target(client, src_msg, normalized_gid, topic_id)
                await message.reply_text("✅ Message copied to target (fallback)")
            except Exception as e2:
                await message.reply_text(f"❌ Failed to forward/copy message: {str(e2)[:100]}")
    except Exception as e:
        logger.error(f"❌ Error in forward (group): {e}")
        await message.reply_text(f"❌ Error: {str(e)[:100]}")


@app.on_message(filters.command("forward") & filters.private)
async def handle_forward_private(client: Client, message: Message):
    """Forward or copy a replied message (in private) to a managed group. Usage: /forward <index_or_id> [topic]
    Reply to a message you sent to the bot or attach a message to forward."""
    try:
        sender = message.from_user
        if not is_admin(sender.id):
            await message.reply_text("❌ Admin only")
            return

        if not message.reply_to_message:
            await message.reply_text("❌ Reply to the message you want to forward (or send/attach it to the bot)")
            return

        args = message.text.split(maxsplit=2)
        if len(args) < 2:
            await message.reply_text("📝 Usage: /forward <index_or_id> [topic]")
            return

        target_str = args[1]
        topic_id_str = args[2] if len(args) >= 3 else None

        group_id, group_id_str, is_index = _get_group_id_from_index(target_str)
        normalized_gid = _normalize_group_id(group_id_str)

        groups = load_managed_groups()
        if group_id_str not in groups and str(normalized_gid) not in groups:
            await message.reply_text(f"❌ Group {target_str} not found in managed groups\nUse /listgroups to see available groups")
            return

        topic_id = None
        if topic_id_str:
            topic_id = await _resolve_topic_id(client, normalized_gid, topic_id_str)
            if not topic_id:
                await message.reply_text(f"⚠️ Could not resolve topic '{topic_id_str}'. Sending to general chat.")

        src_msg = message.reply_to_message
        try:
            if topic_id:
                method = await _attempt_copy_with_thread(client, normalized_gid, src_msg.chat.id, getattr(src_msg, 'message_id', None), topic_id)
            else:
                await client.forward_messages(normalized_gid, src_msg.chat.id, getattr(src_msg, 'message_id', None))
                method = 'forward_messages'

            group_idx = _get_group_index(group_id_str)
            idx_str = f"#{group_idx}" if group_idx > 0 else target_str
            topic_str = f" (topic {topic_id})" if topic_id else ""
            await message.reply_text(f"✅ Message forwarded to group {idx_str}{topic_str} (method: {method})")
            logger.info(f"✅ FORWARD (private): Admin {sender.id} -> {target_str}{topic_str} (method: {method})")
            record_user_interaction(sender, message.chat)
        except Exception as e:
            logger.error(f"❌ Forward error (private): {e}")
            try:
                await _copy_media_to_target(client, src_msg, normalized_gid, topic_id)
                await message.reply_text("✅ Message copied to target (fallback)")
            except Exception as e2:
                await message.reply_text(f"❌ Failed to forward/copy message: {str(e2)[:100]}")
    except Exception as e:
        logger.error(f"❌ Error in forward (private): {e}")
        await message.reply_text(f"❌ Error: {str(e)[:100]}")


@app.on_message(filters.command("broadcast") & filters.private)
async def handle_broadcast(client: Client, message: Message):
    """Broadcast a message to all managed groups. Usage: /broadcast <text> (admin only)"""
    try:
        sender = message.from_user
        if not is_admin(sender.id):
            await message.reply_text("❌ Admin only")
            return

        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            await message.reply_text("❌ Usage: /broadcast <text>")
            return
        text = args[1]

        groups = load_managed_groups()
        if not groups:
            await message.reply_text("📭 No managed groups to broadcast to")
            return

        sent = 0
        failed = []
        for gid in groups.keys():
            try:
                group_id = _normalize_group_id(gid)
                await client.send_message(group_id, text)
                sent += 1
                logger.debug(f"✅ Broadcast sent to group {gid} (as {group_id})")
            except Exception as e:
                logger.error(f"❌ Broadcast to {gid} failed: {str(e)[:100]}")
                failed.append(gid)

        if failed:
            await message.reply_text(f"✅ Broadcast sent to {sent}/{len(groups)} groups\n❌ Failed: {', '.join(failed[:3])}")
        else:
            await message.reply_text(f"✅ Broadcast sent to {sent} groups")
        logger.info(f"✅ BROADCAST: Admin {sender.id} -> {sent}/{len(groups)} groups")
        record_user_interaction(message.from_user, message.chat)
    except Exception as e:
        logger.error(f"❌ Error in broadcast: {e}")
        await message.reply_text("❌ Error broadcasting message")


@app.on_message(filters.command("reply") & filters.private)
async def handle_reply_to_user(client: Client, message: Message):
    """Allow admins to send a DM to any user or list recent users.
    Usage:
      /reply                                    — Show list of recent users to reply to
      /reply <index> <text>                     — Reply to user by index (from /reply list)
      /reply <user_id> <text>                   — Reply by Telegram user ID
      /reply m<msg_id> <text>                   — Reply to sender of message m<msg_id>
      /reply @username <text>                   — Reply by username (if user has one)
    """
    try:
        sender = message.from_user
        if not is_admin(sender.id):
            await message.reply_text("❌ Admin only")
            return

        args = message.text.split(maxsplit=2)
        
        # If no args, show list of recent users
        if len(args) < 2:
            users = load_users()
            if not users:
                await message.reply_text("📭 No users recorded yet")
                return

            sorted_users = sorted(users.values(), key=lambda u: u.get('last_seen', 0), reverse=True)[:30]
            text = "📋 **Recent Users to Reply To:**\n\n"
            for i, u in enumerate(sorted_users, start=1):
                uname = f"@{u['username']}" if u.get('username') else "(no username)"
                first = u.get('first_name', '').strip() or 'Unknown'
                text += f"`{i}️⃣` **{first}** {uname}\n   ID: `{u['id']}`\n\n"

            text += "📌 **Reply using:** `/reply <index> <message>` or `/reply <user_id> <message>`\n"
            text += "   Example: `/reply 1 Hello!` or `/reply 123456789 Hi there!`"
            await message.reply_text(text)
            record_user_interaction(message.from_user, message.chat)
            return

        # We have args: /reply <target> <text>
        if len(args) < 3:
            await message.reply_text("❌ Usage: /reply <index|id|m<msg_id>|@username> <text>\nOr use /reply alone to see user list")
            return

        target = args[1].strip()
        text = args[2]
        user_id = None

        # Try to resolve target in order of priority:
        # 1. Message index (m123)
        if target.lower().startswith('m') and target[1:].isdigit():
            midx = int(target[1:])
            messages = load_messages()
            rec = messages.get(str(midx))
            if rec and rec.get('from_id'):
                user_id = rec['from_id']
                mark_message_handled(midx, sender.id)
                logger.debug(f"Resolved m{midx} to user {user_id}")
        
        # 2. Numeric target (user id or user index)
        if not user_id and target.isdigit():
            uid_int = int(target)
            users = load_users()
            
            # First check if it's a direct user id
            if str(uid_int) in users:
                user_id = uid_int
                logger.debug(f"Resolved {uid_int} as direct user ID")
            else:
                # Try as index from sorted recent users
                sorted_users = sorted(users.values(), key=lambda u: u.get('last_seen', 0), reverse=True)
                idx = uid_int - 1
                if 0 <= idx < len(sorted_users):
                    user_id = sorted_users[idx]['id']
                    logger.debug(f"Resolved index {uid_int} to user {user_id}")
        
        # 3. Username (with or without @)
        if not user_id and (target.startswith('@') or not target.isdigit()):
            users = load_users()
            target_name = target.lstrip('@').lower()
            for u in users.values():
                if u.get('username'):
                    if u['username'].lower() == target_name:
                        user_id = u['id']
                        logger.debug(f"Resolved @{target_name} to user {user_id}")
                        break
            
            # If still not found and target is not a number, try partial match or first name
            if not user_id and not target.isdigit():
                for u in users.values():
                    if u.get('first_name') and u['first_name'].lower() == target_name:
                        user_id = u['id']
                        logger.debug(f"Resolved first_name '{target}' to user {user_id}")
                        break

        if not user_id:
            await message.reply_text("❌ Could not resolve user by index, ID, message, or username.\nUse `/reply` alone to see a list of users.")
            return

        # Get user details for confirmation
        users = load_users()
        user_info = users.get(str(user_id))
        user_display = "Unknown"
        if user_info:
            first_name = user_info.get('first_name', '').strip() or 'User'
            username = user_info.get('username')
            if username:
                user_display = f"{first_name} (@{username})"
            else:
                user_display = f"{first_name} (ID: {user_id})"
        else:
            user_display = f"User {user_id}"

        # Show who we're replying to
        await message.reply_text(f"📤 Sending message to: **{user_display}**")

        await client.send_message(user_id, text)
        await message.reply_text(f"✅ ✓ Message delivered to **{user_display}**")
        logger.info(f"✅ REPLY: Admin {sender.id} -> {user_display} ({user_id})")
        record_user_interaction(message.from_user, message.chat)
    except Exception as e:
        logger.error(f"❌ Error in reply: {e}")
        await message.reply_text(f"❌ Error sending reply: {str(e)[:100]}")


@app.on_message(filters.command("inbox") & filters.private)
async def handle_inbox(client: Client, message: Message):
    """List unhandled messages for admins."""
    try:
        if not is_admin(message.from_user.id):
            await message.reply_text("❌ Admin only")
            logger.info(f"⚠️ Non-admin {message.from_user.id} tried /inbox")
            return

        logger.info(f"✅ INBOX: Admin {message.from_user.id} checking inbox")
        messages = load_messages()
        if not messages:
            await message.reply_text("📭 No messages recorded")
            return

        # filter unhandled
        items = [m for m in messages.values() if not m.get('handled')]
        if not items:
            await message.reply_text("📭 No pending messages")
            return

        items_sorted = sorted(items, key=lambda m: m.get('date', 0), reverse=True)[:50]
        text = "📥 **Pending Messages:**\n\n"
        for m in items_sorted:
            mid = m.get('id', 0)
            name = m.get('from_first') or ''
            uname = ('@'+m.get('from_username')) if m.get('from_username') else ''
            preview = (m.get('text') or '')[:140]
            if mid and mid > 0:
                text += f"m{mid}: {name} {uname} — {preview}\n"
            else:
                text += f"(unindexed): {name} {uname} — {preview}\n"

        text += "\nUse /view m<id> to view/copy the original message, or /reply m<id> <text> to reply."
        await message.reply_text(text)
    except Exception as e:
        logger.error(f"❌ Error in inbox: {e}")
        await message.reply_text("❌ Error listing inbox")


@app.on_message(filters.command("view") & filters.private)
async def handle_view_message(client: Client, message: Message):
    """Copy the original message into admin chat so they can see full context."""
    try:
        if not is_admin(message.from_user.id):
            await message.reply_text("❌ Admin only")
            logger.info(f"⚠️ Non-admin {message.from_user.id} tried /view")
            return

        logger.info(f"✅ VIEW: Admin {message.from_user.id} viewing message")
        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            await message.reply_text("❌ Usage: /view m<id> or /view <id>")
            return
        key = args[1].lstrip()
        # Accept both m123 and 123 formats
        if key.lower().startswith('m'):
            key_id = key[1:]
        else:
            key_id = key
        
        if key_id.isdigit():
            midx = int(key_id)
            messages = load_messages()
            rec = messages.get(str(midx))
            if not rec:
                await message.reply_text("❌ Message not found")
                return
            cid = rec.get('chat_id')
            mid = rec.get('message_id')
            if cid and mid:
                try:
                    await client.copy_message(message.chat.id, int(cid), int(mid))
                except Exception:
                    await message.reply_text(f"Could not copy original message. Preview:\n{rec.get('text')}")
            else:
                await message.reply_text(f"Original not available. Preview:\n{rec.get('text')}")
        else:
            await message.reply_text("❌ Usage: /view m<id> or /view <id>")
    except Exception as e:
        logger.error(f"❌ Error in view: {e}")
        await message.reply_text("❌ Error viewing message")


@app.on_message(filters.command("resolve") & filters.private)
async def handle_resolve_message(client: Client, message: Message):
    """Mark a message as handled without replying: /resolve m<id>"""
    try:
        if not is_admin(message.from_user.id):
            await message.reply_text("❌ Admin only")
            logger.info(f"⚠️ Non-admin {message.from_user.id} tried /resolve")
            return
        logger.info(f"✅ RESOLVE: Admin {message.from_user.id} resolving message")
        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            await message.reply_text("❌ Usage: /resolve m<id> or /resolve <id>")
            return
        key = args[1].lstrip()
        # Accept both m123 and 123 formats
        if key.lower().startswith('m'):
            key_id = key[1:]
        else:
            key_id = key
        
        if key_id.isdigit():
            midx = int(key_id)
            if midx <= 0:
                await message.reply_text("❌ Invalid message id")
                return
            ok = mark_message_handled(midx, message.from_user.id)
            if ok:
                await message.reply_text(f"✅ Marked m{midx} as handled")
            else:
                await message.reply_text("❌ Could not mark as handled")
        else:
            await message.reply_text("❌ Usage: /resolve m<id> or /resolve <id>")
    except Exception as e:
        logger.error(f"❌ Error in resolve: {e}")
        await message.reply_text("❌ Error resolving message")


# ==================== Auto-Register Groups ====================

@app.on_message(filters.service)
async def handle_auto_register(client: Client, message: Message):
    """Auto-register groups/channels when bot is added by an admin"""
    try:
        # Detect if bot was added to a group/channel
        if (message.new_chat_members and 
            any(m.is_bot and m.username == BOT_USERNAME for m in message.new_chat_members)):
            
            # Check if the user who added the bot is an admin
            if not await _is_chat_admin(client, message.chat.id, message.from_user.id):
                logger.info(f"⚠️ {BOT_USERNAME} added by non-admin in {message.chat.id}")
                return
            
            group_id = message.chat.id
            group_name = message.chat.title or f"Group {group_id}"
            groups = load_managed_groups()
            
            if str(group_id) not in groups:
                # Auto-register
                add_managed_group(group_id, group_name)
                logger.info(f"✅ AUTO-REGISTERED: {group_name} ({group_id})")
                
                try:
                    await message.reply_text(f"✅ **{BOT_USERNAME}** auto-registered as admin bot in **{group_name}**\n"
                                            f"Use /groupinfo to see group info and admin commands available")
                except Exception:
                    logger.debug(f"Could not send confirmation message in {group_id}")
    except Exception as e:
        logger.debug(f"Error in auto_register: {e}")


# ==================== Admin Commands (must be BEFORE capture handlers) ====================


@app.on_message(filters.command("testpurge") & filters.group)
async def handle_test_purge(client: Client, message: Message):
    """Test command to check if group commands work"""
    try:
        logger.info(f"🔥 TESTPURGE COMMAND RECEIVED: {message.text} from {message.from_user.id} in chat {message.chat.id}")
        await message.reply_text("🔥 Test command works! Group commands are being processed.")
    except Exception as e:
        logger.error(f"❌ Error in testpurge: {e}")


@app.on_message(filters.command("unban") & filters.group)
async def handle_unban(client: Client, message: Message):
    """Unban a user from the group. Only admins can use this command.
    
    Usage: /unban @username or reply to user with /unban
    """
    try:
        if not message.from_user:
            await message.reply_text("❌ Unable to verify user identity")
            return
        
        # Check if user is admin
        is_admin_check = await _is_chat_admin(client, message.chat.id, message.from_user.id)
        if not is_admin_check:
            await message.reply_text("❌ Only group admins can use /unban")
            return
        
        target_user = None
        target_username = None
        
        # Try to get user from reply
        if message.reply_to_message and message.reply_to_message.from_user:
            target_user = message.reply_to_message.from_user
            target_username = target_user.username if target_user.username else f"user_{target_user.id}"
        else:
            # Try to get user from command text
            cmd_text = message.text or ""
            parts = cmd_text.split()
            
            if len(parts) > 1:
                username_part = parts[1]
                if username_part.startswith('@'):
                    target_username = username_part[1:]
                else:
                    target_username = username_part
        
        if not target_username:
            await message.reply_text("❌ Please reply to a user or mention @username")
            return
        
        try:
            # Unban the user
            await client.unban_chat_member(message.chat.id, target_user.id if target_user else target_username)
            
            if target_user:
                await message.reply_text(f"✅ Unbanned {target_user.first_name} (@{target_username})")
                logger.info(f"✅ UNBAN: Admin {message.from_user.id} unbanned {target_user.id} from {message.chat.id}")
            else:
                await message.reply_text(f"✅ Unbanned @{target_username}")
                logger.info(f"✅ UNBAN: Admin {message.from_user.id} unbanned @{target_username} from {message.chat.id}")
                
        except Exception as e:
            await message.reply_text(f"❌ Failed to unban user: {str(e)[:100]}")
            logger.error(f"❌ Unban error: {e}")
            
    except Exception as e:
        logger.error(f"❌ Error in unban: {e}")
        await message.reply_text(f"❌ Error: {str(e)[:100]}")


@app.on_message(filters.command("restrict") & filters.group)
async def handle_restrict(client: Client, message: Message):
    """Restrict a user's permissions in the group. Only admins can use this command.
    
    Usage: /restrict (reply to user)
    - Restricts user from sending messages and media
    """
    try:
        if not message.from_user:
            await message.reply_text("❌ Unable to verify user identity")
            return
        
        # Check if user is admin
        is_admin_check = await _is_chat_admin(client, message.chat.id, message.from_user.id)
        if not is_admin_check:
            await message.reply_text("❌ Only group admins can use /restrict")
            return
        
        # Get target user from reply
        if not message.reply_to_message or not message.reply_to_message.from_user:
            await message.reply_text("❌ Reply to a user's message to restrict them")
            return
        
        target_user = message.reply_to_message.from_user
        user_id = target_user.id
        
        try:
            # Restrict the user (no messages, no media)
            await client.restrict_chat_member(
                message.chat.id,
                user_id,
                ChatPermissions(
                    can_send_messages=False,
                    can_send_media_messages=False,
                    can_send_other_messages=False,
                    can_add_web_page_previews=False
                )
            )
            
            await message.reply_text(f"⚠️ Restricted {target_user.first_name} (@{target_user.username or 'N/A'})")
            logger.info(f"✅ RESTRICT: Admin {message.from_user.id} restricted {user_id} in {message.chat.id}")
            
        except Exception as e:
            await message.reply_text(f"❌ Failed to restrict user: {str(e)[:100]}")
            logger.error(f"❌ Restrict error: {e}")
            
    except Exception as e:
        logger.error(f"❌ Error in restrict: {e}")
        await message.reply_text(f"❌ Error: {str(e)[:100]}")


@app.on_message(filters.command("unrestrict") & filters.group)
async def handle_unrestrict(client: Client, message: Message):
    """Remove restrictions from a user in the group. Only admins can use this command.
    
    Usage: /unrestrict (reply to user)
    - Restores full user permissions
    """
    try:
        if not message.from_user:
            await message.reply_text("❌ Unable to verify user identity")
            return
        
        # Check if user is admin
        is_admin_check = await _is_chat_admin(client, message.chat.id, message.from_user.id)
        if not is_admin_check:
            await message.reply_text("❌ Only group admins can use /unrestrict")
            return
        
        # Get target user from reply
        if not message.reply_to_message or not message.reply_to_message.from_user:
            await message.reply_text("❌ Reply to a user's message to unrestrict them")
            return
        
        target_user = message.reply_to_message.from_user
        user_id = target_user.id
        
        try:
            # Remove all restrictions
            await client.restrict_chat_member(
                message.chat.id,
                user_id,
                ChatPermissions(
                    can_send_messages=True,
                    can_send_media_messages=True,
                    can_send_other_messages=True,
                    can_add_web_page_previews=True
                )
            )
            
            await message.reply_text(f"✅ Unrestricted {target_user.first_name} (@{target_user.username or 'N/A'})")
            logger.info(f"✅ UNRESTRICT: Admin {message.from_user.id} unrestricted {user_id} in {message.chat.id}")
            
        except Exception as e:
            await message.reply_text(f"❌ Failed to unrestrict user: {str(e)[:100]}")
            logger.error(f"❌ Unrestrict error: {e}")
            
    except Exception as e:
        logger.error(f"❌ Error in unrestrict: {e}")
        await message.reply_text(f"❌ Error: {str(e)[:100]}")


@app.on_message(filters.command("clearinbox") & filters.private)
async def handle_clearinbox(client: Client, message: Message):
    """Clear inbox messages. Only admins can use this command.
    
    Usage: /clearinbox [count]
    - If count is provided, deletes that many recent messages
    - If no count, deletes all pending messages
    - Marks messages as handled so they don't appear in inbox
    """
    try:
        logger.info(f"🗑️ CLEARINBOX COMMAND RECEIVED: {message.text} from {message.from_user.id}")
        
        if not is_admin(message.from_user.id):
            await message.reply_text("❌ Admin only")
            return
        
        # Parse count argument
        cmd_text = message.text or ""
        args = cmd_text.split()
        count = None
        
        if len(args) > 1:
            try:
                count = int(args[1])
                if count <= 0:
                    count = None
            except ValueError:
                await message.reply_text("❌ Invalid count. Use: /clearinbox [number]")
                return
        
        # Load messages
        messages = load_messages()
        if not messages:
            await message.reply_text("📭 No messages in inbox")
            return
        
        # Filter unhandled messages
        unhandled = [mid for mid, info in messages.items() if not info.get('handled', False)]
        
        if not unhandled:
            await message.reply_text("📭 No pending messages to clear")
            return
        
        # Determine how many to clear
        messages_to_clear = unhandled[:count] if count else unhandled
        
        # Mark messages as handled
        cleared_count = 0
        for mid in messages_to_clear:
            if mid in messages:
                messages[mid]['handled'] = True
                cleared_count += 1
        
        # Save updated messages
        save_messages(messages)
        
        await message.reply_text(f"🗑️ Cleared {cleared_count} messages from inbox")
        logger.info(f"✅ CLEARINBOX: Admin {message.from_user.id} cleared {cleared_count} messages")
        
    except Exception as e:
        logger.error(f"❌ Error in clearinbox: {e}")
        await message.reply_text(f"❌ Error: {str(e)[:100]}")


# ==================== Generic Capture Handlers (at END to not block commands) ====================


@app.on_message(filters.private)
async def capture_private_messages(client: Client, message: Message):
    """Capture any private messages from users to allow admins to review and reply later."""
    try:
        # ignore commands, bot messages, and ADMIN messages (admins are internal)
        if message.text and message.text.startswith('/'):
            return
        if message.from_user and getattr(message.from_user, 'is_bot', False):
            return
        if is_admin(message.from_user.id):
            # Don't capture admin-to-admin messages
            return
        # record user interaction & message
        record_user_interaction(message.from_user, message.chat)
        mid = add_message_record(message)
        # only notify admins if we got a valid positive id
        if mid and mid > 0:
            for aid in ADMINS:
                try:
                    preview = (message.text or getattr(message, 'caption', '') or '')[:200]
                    await client.send_message(aid, f"📨 New message m{mid} from {message.from_user.first_name} ({message.from_user.id}):\n{preview}\nUse /inbox to list or /view m{mid} to view")
                except Exception:
                    logger.debug(f"Couldn't notify admin {aid} about message {mid}")
        else:
            # if we couldn't assign a regular index, notify admins without exposing 'm0'
            for aid in ADMINS:
                try:
                    preview = (message.text or getattr(message, 'caption', '') or '')[:200]
                    await client.send_message(aid, f"📨 New message (unindexed) from {message.from_user.first_name} ({message.from_user.id}):\n{preview}\nUse /inbox to list or /view to view")
                except Exception:
                    logger.debug(f"Couldn't notify admin {aid} about unindexed message")
    except Exception as e:
        logger.error(f"❌ Error capturing private message: {e}")


@app.on_message(filters.group)
async def capture_group_mentions(client: Client, message: Message):
    """Capture group messages that mention the bot or are replies to the bot."""
    try:
        # ignore bot messages and commands
        if message.from_user and getattr(message.from_user, 'is_bot', False):
            return
        
        # ignore all commands (starting with /)
        if message.text and message.text.startswith('/'):
            return

        mentioned = False
        text = message.text or message.caption or ''
        if BOT_USERNAME and BOT_USERNAME.lower() in (text or '').lower():
            mentioned = True
        # reply to a bot message
        if message.reply_to_message and message.reply_to_message.from_user and getattr(message.reply_to_message.from_user, 'is_self', False):
            mentioned = True

        if not mentioned:
            return

        record_user_interaction(message.from_user, message.chat)
        mid = add_message_record(message)
        if mid and mid > 0:
            for aid in ADMINS:
                try:
                    preview = (text or '')[:200]
                    await client.send_message(aid, f"📨 New group message m{mid} from {message.from_user.first_name} in {message.chat.title or message.chat.id}:\n{preview}\nUse /view m{mid} to view the original message")
                except Exception:
                    logger.debug(f"Couldn't notify admin {aid} about group message {mid}")
        else:
            for aid in ADMINS:
                try:
                    preview = (text or '')[:200]
                    await client.send_message(aid, f"📨 New group message (unindexed) from {message.from_user.first_name} in {message.chat.title or message.chat.id}:\n{preview}")
                except Exception:
                    logger.debug(f"Couldn't notify admin {aid} about group message (unindexed)")
    except Exception as e:
        logger.error(f"❌ Error capturing group mention: {e}")


if __name__ == "__main__":
    try:
        logger.info("🚀 STARTING SigmaChanBot")
        # Start client, configure bot commands for scopes, then idle
        app.start()
        app.loop.run_until_complete(set_bot_commands_for_scopes(app))
        idle()
        app.stop()
    except KeyboardInterrupt:
        logger.info("⏹️  BOT STOPPED")
    except Exception as e:
        logger.error(f"❌ CRITICAL ERROR: {e}")
        raise
