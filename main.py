#
# bot.py
#
# Twitter@Lakr233
# 2023-03-18
#

import os
import re
import torch
import json
import datetime
from transformers import AutoTokenizer, AutoModel
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler


print(f"[+] welcome to chat bot")

script_path = os.path.dirname(os.path.realpath(__file__))
os.chdir(script_path)

token = 'aaaaaaaaaa:88888888888888888888888888888888888'
admin_id = ['000000000']
fine_granted_identifier = []

# load from fine_granted_identifier.json if exists
try:
    with open('fine_granted_identifier.json', 'r') as f:
        fine_granted_identifier = json.load(f)
except Exception as e:
    print(f"[!] error loading fine_granted_identifier.json: {e}")
    pass

print("[+] loading model...")
model_path = os.path.join(script_path, 'model')

print("[+] model path: {}".format(model_path))

tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
print("[+] tokenizer loaded")
model = AutoModel.from_pretrained(
    model_path, trust_remote_code=True).half().cuda()
print("[+] model loaded")

model = model.eval()

class Chat:
    user_id = ''
    history = []
    last_message_time = datetime.datetime.now()

    def __init__(self, user_id):
        self.user_id = user_id
        self.history = []

    def chat(self, query) -> str:
        self.last_message_time = datetime.datetime.now()
        try:
            response, self.history = model.chat(tokenizer, query, history=self.history, max_length=16384) # let the cuda crash so we clear the history
            if len(response) <= 0: raise Exception("empty response")
            return response
        except Exception as e:
            print(f"[!] error chatting: {e}")
            self.history = []
            return "An error occurred, please try again later. Your conversation history has been reset."
        finally:
            torch.cuda.empty_cache()

    def finalize_resp_text(self, input) -> str:
        output = input

        char_map_for_chinese = {
            ',': '，',
            '.': '。',
            '?': '？',
            '!': '！',
            ':': '：',
            ';': '；',
            '(': '（',
            ')': '）',
            '\‘': '‘',
            '\’': '’',
            '\“': '“',
            '\”': '”',
        }
        
        for idx, ch in enumerate(output):
            if ch in char_map_for_chinese:
                prev_idx = idx - 1
                if prev_idx < 0: continue
                prev_ch = output[prev_idx]
                # if prev is Chinese do the replacement
                if re.match(r'[\u4e00-\u9fff]', prev_ch):
                    output = output[:idx] + char_map_for_chinese[ch] + output[idx + 1:]

        return output

    def reset(self):
        self.history = []


chat_context_container = {}

print("[+] booting bot...")


def validate_user(update: Update) -> bool:
    identifier = user_identifier(update)
    if identifier in admin_id:
        return True
    if identifier in fine_granted_identifier:
        return True
    return False

def check_timestamp(update: Update) -> bool:
    # check timestamp
    global boot_time
    # if is earlier than boot time, ignore
    message_utc_timestamp = update.message.date.timestamp()
    boot_utc_timestamp = boot_time.timestamp()
    if message_utc_timestamp < boot_utc_timestamp:
        return False
    return True

def check_should_handle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if update.message is None or update.message.text is None or len(update.message.text) == 0:
        return False

    if check_timestamp(update) is False:
        print(f"[-] Message timestamp is earlier than boot time, ignoring")
        return False

    # if mentioning ourself, at the beginning of the message
    if update.message.entities is not None:
        for entity in update.message.entities:
            if (
                True
                and (entity.type is not None)
                and (entity.type == "mention")
                # and (entity.user is not None)
                # and (entity.user.id is not None)
                # and (entity.user.id == context.bot.id)
            ):
                mention_text = update.message.text[entity.offset:entity.offset + entity.length]
                if not mention_text == f"@{context.bot.username}":
                    continue
                print(f"[i] Handling incoming message with reason 'mention'")
                return True

    # if replying to ourself
    if (
        True
        and (update.message.reply_to_message is not None)
        and (update.message.reply_to_message.from_user is not None)
        and (update.message.reply_to_message.from_user.id is not None)
        and (update.message.reply_to_message.from_user.id == context.bot.id)
    ):
        print(f"[i] Handling incoming message with reason 'reply'")
        return True

    # if is a private chat
    if update.effective_chat.type == "private":
        print(f"[i] Handling incoming message with reason 'private chat'")
        return True

    return False


def user_identifier(update: Update) -> str:
    return f"{update.effective_chat.id}"


async def reset_chat(update: Update, context):
    if not validate_user(update):
        await update.message.reply_text('Sadly, you are not allowed to use this bot at this time.')
        return
    if check_timestamp(update) is False: return

    user_id = user_identifier(update)
    if user_id in chat_context_container:
        chat_context_container[user_id].reset()
        await update.message.reply_text('Chat history has been reset')
    else:
        await update.message.reply_text('Chat history is empty')


async def recv_msg(update: Update, context):
    if not check_should_handle(update, context): return
    if not validate_user(update):
        await update.message.reply_text('Sadly, you are not allowed to use this bot at this time.')
        return

    chat_session = chat_context_container.get(user_identifier(update))
    if chat_session is None:
        chat_session = Chat(user_identifier(update))
        chat_context_container[user_identifier(update)] = chat_session

    print(f"[i] {update.effective_user.username} said: {update.message.text}")

    message = await update.message.reply_text(
        '... thinking ...'
    )
    if message is None:
        print("[!] failed to send message")
        return
    
    try:
        input_text = update.message.text
        # remove bot name from text with @
        pattern = f"@{context.bot.username}"
        input_text = input_text.replace(pattern, '')
        response = chat_session.chat(input_text)
        response = chat_session.finalize_resp_text(response)
        print(f"[i] {update.effective_user.username} reply: {response}")
        await message.edit_text(response)
    except Exception as e:
        print(f"[!] error: {e}")
        chat_session.reset()
        await message.edit_text('Error orrurred, please try again later. Your chat history has been reset.')

async def start_bot(update: Update, context):
    if check_timestamp(update) is False: return
    id = user_identifier(update)
    welcome_strs = [
        'Welcome to THUDM/ChatGLM-6B made with love by Twitter@Lakr233!',
        '',
        'Command: /id to get your chat identifier',
        'Command: /reset to reset the chat history',
    ]
    if id in admin_id:
        extra = [
            '',
            'Admin Command: /grant to grant fine-granted access to a user',
            'Admin Command: /ban to ban a user',
            'Admin Command: /status to report the status of the bot',
            'Admin Command: /reboot to clear all chat history',
        ]
        welcome_strs.extend(extra)
    print(f"[i] {update.effective_user.username} started the bot")
    await update.message.reply_text('\n'.join(welcome_strs))


async def send_id(update: Update, context):
    if check_timestamp(update) is False: return
    current_identifier = user_identifier(update)
    await update.message.reply_text(f'Your chat identifier is {current_identifier}, send it to the bot admin to get fine-granted access.')

async def grant(update: Update, context):
    if check_timestamp(update) is False: return
    current_identifier = user_identifier(update)
    if current_identifier not in admin_id:
        await update.message.reply_text('You are not admin!')
        return
    if len(context.args) != 1:
        await update.message.reply_text('Please provide a user id to grant!')
        return
    user_id = context.args[0].strip()
    if user_id in fine_granted_identifier:
        await update.message.reply_text('User already has fine-granted access!')
        return
    fine_granted_identifier.append(user_id)
    with open('fine_granted_identifier.json', 'w') as f:
        json.dump(list(fine_granted_identifier), f)
    await update.message.reply_text('User has been granted fine-granted access!')

async def ban(update: Update, context):
    if check_timestamp(update) is False: return
    current_identifier = user_identifier(update)
    if current_identifier not in admin_id:
        await update.message.reply_text('You are not admin!')
        return
    if len(context.args) != 1:
        await update.message.reply_text('Please provide a user id to ban!')
        return
    user_id = context.args[0].strip()
    if user_id in fine_granted_identifier:
        fine_granted_identifier.remove(user_id)
    if user_id in chat_context_container:
        del chat_context_container[user_id]
    with open('fine_granted_identifier.json', 'w') as f:
        json.dump(list(fine_granted_identifier), f)
    await update.message.reply_text('User has been banned!')

async def status(update: Update, context):
    if check_timestamp(update) is False: return
    current_identifier = user_identifier(update)
    if current_identifier not in admin_id:
        await update.message.reply_text('You are not admin!')
        return
    report = [
        'Status Report:',
        f'[+] bot started at {boot_time}',
        f'[+] admin users: {admin_id}',
        f'[+] fine-granted users: {len(fine_granted_identifier)}',
        f'[+] chat sessions: {len(chat_context_container)}',
        '',
    ]
    # list each fine-granted user
    cnt = 1
    for user_id in fine_granted_identifier:
        report.append(f'[i] {cnt} {user_id}')
        cnt += 1
    await update.message.reply_text(
        '```\n' + '\n'.join(report) + '\n```',
        parse_mode=ParseMode.MARKDOWN_V2,
    )

async def reboot(update: Update, context):
    if check_timestamp(update) is False: return
    current_identifier = user_identifier(update)
    if current_identifier not in admin_id:
        await update.message.reply_text('You are not admin!')
        return
    chat_context_container.clear()
    await update.message.reply_text('All chat history has been cleared!')

boot_time = datetime.datetime.now()

print(f"[+] bot started at {boot_time}, calling loop!")
application = ApplicationBuilder().token(token).build()

handler_list = [
    CommandHandler('id', send_id),
    CommandHandler('start', start_bot),
    CommandHandler('help', start_bot),
    CommandHandler('reset', reset_chat),
    CommandHandler('grant', grant),
    CommandHandler('ban', ban),
    CommandHandler('status', status),
    CommandHandler('reboot', reboot),
    MessageHandler(None, recv_msg),
]
for handler in handler_list:
    application.add_handler(handler)

application.run_polling()