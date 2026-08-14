import logging
import asyncio
import sqlite3
import re
import hashlib
import os
from docx import Document
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiohttp import web # RENDER BEPUL PORTI UCHUN

logging.basicConfig(level=logging.INFO)

TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=TOKEN)
dp = Dispatcher()

# RENDER BEPUL TARIFI PORTINI ALDASH UCHUN VIRTUAL SERVER
async def handle(request):
    return web.Response(text="Bot is running smoothly!")

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', handle)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 10000))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"Virtual veb-server {port} portida ishga tushdi!")

def init_db():
    conn = sqlite3.connect("quiz.db")
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS tests 
                      (id INTEGER PRIMARY KEY AUTOINCREMENT, subject TEXT, question TEXT, options TEXT, correct_index INTEGER)''')
    conn.commit()
    conn.close()

def get_subject_id(subject_name):
    return hashlib.md5(str(subject_name).encode('utf-8')).hexdigest()[:10]

def import_from_word():
    conn = sqlite3.connect("quiz.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM tests")
    
    try:
        if not os.path.exists("testlar.docx"):
            print("Xatolik: testlar.docx fayli topilmadi!")
            return
            
        doc = Document("testlar.docx")
        lines = []
        for p in doc.paragraphs:
            txt = p.text.strip()
            if txt:
                lines.append(txt)
                
        current_subject = "Umumiy testlar"
        current_question = None
        current_options = []
        correct_index = -1
        
        for line in lines:
            # 1. Mavzuni aniqlash
            if re.match(r'(?i)^Mavzu:\s*(.*)', line):
                current_subject = re.match(r'(?i)^Mavzu:\s*(.*)', line).group(1).strip()
                continue
            
            # 2. Savolni aniqlash (Masalan: 1. yoki 1) boshlansa)
            q_match = re.match(r'^(\d+)[\.\s\)]+\s*(.*)', line)
            if q_match:
                # Agar avvalgi savol to'liq yig'ilgan bo'lsa, bazaga saqlaymiz
                if current_question and len(current_options) >= 2 and correct_index != -1:
                    cursor.execute("INSERT INTO tests (subject, question, options, correct_index) VALUES (?, ?, ?, ?)",
                                   (current_subject, current_question, "&&".join(current_options), correct_index))
                
                # Yangi savolni boshlaymiz
                current_question = q_match.group(2).strip()
                current_options = []
                correct_index = -1
                continue
                
            # 3. Variantlarni aniqlash (A), B), C), D) yoki A. B. C. D.)
            opt_match = re.match(r'^([A-DXZa-dxz])[\)\.\s]+\s*(.*)', line)
            if opt_match and current_question:
                opt_text = opt_match.group(2).strip()
                current_options.append(opt_text)
                continue
                
            # 4. To'g'ri javobni aniqlash (Жавоб: A yoki Javob: B)
            ans_match = re.match(r'(?i)^(Javob|Жавоб|To\'g\'ri javob|Тўғри жавоб):\s*([A-DXZa-dxz])', line)
            if ans_match and current_question:
                ans_letter = ans_match.group(2).upper()
                # Oxirgi variantlardan to'g'ri indeksni aniqlaymiz
                correct_index = ord(ans_letter) - ord('A')
                continue

        # Eng oxirgi savolni ham bazaga yuklaymiz
        if current_question and len(current_options) >= 2 and correct_index != -1:
            cursor.execute("INSERT INTO tests (subject, question, options, correct_index) VALUES (?, ?, ?, ?)",
                           (current_subject, current_question, "&&".join(current_options), correct_index))
            
        conn.commit()
        print("Word fayli muvaffaqiyatli yuklandi!")
    except Exception as e:
        print("Word xatolik:", e)
    finally:
        conn.close()

@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    conn = sqlite3.connect("quiz.db")
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT subject FROM tests")
    subjects = cursor.fetchall()
    conn.close()
    
    if not subjects:
        await message.answer("Bazada testlar topilmadi. Iltimos, administrator bilan bog'laning.")
        return
        
    builder = InlineKeyboardBuilder()
    for sub in subjects:
        sub_name = sub[0]
        builder.button(text=f"📂 {sub_name}", callback_data=f"sub_{get_subject_id(sub_name)}")
    builder.adjust(1)
    await message.answer("Assalomu alaykum! Mavzulardan birini tanlang va haqiqiy Telegram Quiz testini boshlang:", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("sub_") | F.data.startswith("nxt_"))
async def send_telegram_quiz(callback: types.CallbackQuery):
    target_sub_id = callback.data.split("_")[1]
    conn = sqlite3.connect("quiz.db")
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT subject FROM tests")
    all_subjects = cursor.fetchall()
    subject_name = None
    for sub in all_subjects:
        if get_subject_id(sub[0]) == target_sub_id:
            subject_name = sub[0]
            break
            
    if not subject_name:
        await callback.message.answer("Mavzu topilmadi.")
        conn.close()
        return
        
    cursor.execute("SELECT question, options, correct_index FROM tests WHERE subject=? ORDER BY RANDOM() LIMIT 1", (subject_name,))
    question_data = cursor.fetchone()
    conn.close()
    
    if question_data:
        question, options, correct_index = question_data
        options_list = options.split("&&")
        
        await callback.message.answer_poll(
            question=f"📋 Mavzu: {subject_name}\n\n{question}"[:250],
            options=[opt[:100] for opt in options_list],
            type="quiz",
            correct_option_id=correct_index,
            is_anonymous=False,
            open_period=45
        )
        
        builder = InlineKeyboardBuilder()
        builder.button(text="Keyingi savol ➡️", callback_data=f"nxt_{target_sub_id}")
        builder.button(text="Menu 🏠", callback_data="back_to_menu")
        builder.adjust(1)
        await callback.message.answer("Savolga javob berib, keyingisiga o'tish tugmasini bosing:", reply_markup=builder.as_markup())
        try: await callback.message.delete()
        except: pass
    else:
        await callback.message.answer(f"📋 {subject_name} mavzusida testlar tugadi. Yangi mavzu uchun /start bosing.")

@dp.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: types.CallbackQuery):
    conn = sqlite3.connect("quiz.db")
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT subject FROM tests")
    subjects = cursor.fetchall()
    conn.close()
    
    builder = InlineKeyboardBuilder()
    for sub in subjects:
        sub_name = sub[0]
        builder.button(text=f"📂 {sub_name}", callback_data=f"sub_{get_subject_id(sub_name)}")
    builder.adjust(1)
    await callback.message.answer("Iltimos, test yechmoqchi bo'lgan **mavzuni tanlang**:", reply_markup=builder.as_markup())
    try: await callback.message.delete()
    except: pass

async def main():
    init_db()
    import_from_word()
    await asyncio.gather(start_web_server(), dp.start_polling(bot))

if __name__ == "__main__":
    asyncio.run(main())
