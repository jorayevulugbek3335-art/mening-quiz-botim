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
from aiohttp import web

logging.basicConfig(level=logging.INFO)

TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=TOKEN)
dp = Dispatcher()

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
        
        # Word ichidagi barcha matnlarni oddiy qatorlarga yig'amiz
        for p in doc.paragraphs:
            if p.text.strip(): lines.append(p.text.strip())
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for p in cell.paragraphs:
                        if p.text.strip() and p.text.strip() not in lines:
                            lines.append(p.text.strip())

        current_subject = "Umumiy testlar"
        current_question = ""
        options = []
        
        for text in lines:
            # Mavzuni aniqlash
            if text.lower().startswith("mavzu:") or text.lower().startswith("bo'lim:"):
                current_subject = text.split(":")[-1].strip()
                continue
                
            # Savolni aniqlash
            if re.match(r'^\d+[\.\s\)]', text):
                current_question = re.sub(r'^\d+[\.\s\)]\s*', '', text).strip()
                options = []
                continue
                
            # Variantlarni aniqlash
            if re.match(r'^[A-DXZa-dxz][\)\.]', text):
                clean_opt = re.sub(r'^[A-DXZa-dxz][\)\.]\s*', '', text).strip()
                # Agar variant ichiga "Javob:" yopishib ketgan bo'lsa tozalaymiz
                clean_opt = re.split(r'(?i)(Javob:|Жавоб:|To\'g\'ri javob:|Тўғри жавоб:)', clean_opt)[0].strip()
                if clean_opt and clean_opt not in options:
                    options.append(clean_opt)
                    
            # To'g'ri javobni aniqlash va bazaga saqlash
            if "javob:" in text.lower() or "жавоб:" in text.lower():
                ans_match = re.search(r'(?i)(?:Javob|Жавоб|To\'g\'ri javob|Тўғри жавоб):\s*([A-DXZa-dxz])', text)
                if ans_match and current_question and len(options) >= 2:
                    ans_letter = ans_match.group(1).upper()
                    correct_index = ord(ans_letter) - ord('A')
                    if 0 <= correct_index < len(options):
                        cursor.execute("INSERT INTO tests (subject, question, options, correct_index) VALUES (?, ?, ?, ?)",
                                       (current_subject, current_question, "&&".join(options), correct_index))
                        conn.commit()

        print("Word fayli muvaffaqiyatli yuklandi va bazaga yozildi!")
    except Exception as e:
        print("Word faylini o'qishda xatolik:", e)
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
        await message.answer("Bazada testlar topilmadi. Iltimos, Word faylingizni va kodingizni qayta tekshiring.")
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
            open_period=30
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
