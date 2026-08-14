import logging
import asyncio
import sqlite3
import re
import hashlib
from docx import Document
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

logging.basicConfig(level=logging.INFO)

# BOT TOKEN (BotFather'dan olgan tokeningizni yozing)
TOKEN = "8629248865:AAE4iBnZy3q7SSIy_WAooQEIXv340BDeqF4"
bot = Bot(token=TOKEN)
dp = Dispatcher()

def init_db():
    conn = sqlite3.connect("quiz.db")
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS tests 
                      (id INTEGER PRIMARY KEY AUTOINCREMENT, subject TEXT, question TEXT, options TEXT, correct_index INTEGER)''')
    conn.commit()
    conn.close()

def get_subject_id(subject_name):
    # Bu yerda subject_name matn (str) ekanligiga ishonch hosil qilamiz
    return hashlib.md5(str(subject_name).encode('utf-8')).hexdigest()[:10]

def import_from_word():
    conn = sqlite3.connect("quiz.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM tests")
    
    try:
        doc = Document("testlar.docx")
        full_text = []
        
        for p in doc.paragraphs:
            if p.text.strip():
                full_text.append(p.text.strip())
                
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    if cell.text.strip():
                        full_text.append(cell.text.strip())

        current_subject = "Umumiy testlar"
        text_dump = "\n".join(full_text)
        
        blocks = re.split(r'(?i)Mavzu:\s*', text_dump)
        
        for block in blocks:
            if not block.strip():
                continue
            
            lines = block.split("\n")
            if not re.match(r'^\d+[\.\)]', lines[0]) and not lines[0].strip().startswith(("A)", "B)", "C)", "D)")):
                current_subject = lines[0].strip()
                block_content = "\n".join(lines[1:])
            else:
                block_content = "\n".join(lines)
            
            questions_raw = re.split(r'\n(?=\d+[\.\s\)])|^(?=\d+[\.\s\)])', block_content)
            
            for q_raw in questions_raw:
                q_text = q_raw.strip()
                if not q_text:
                    continue
                
                q_match = re.match(r'^\d+[\.\s\)]\s*(.*?)(?=[A-DXZa-dxz][\)\.])', q_text, re.DOTALL)
                if not q_match:
                    continue
                
                question_body = q_match.group(1).strip()
                options = re.findall(r'(?:[A-DXZa-dxz][\)\.]\s*)(.*?)(?=[A-DXZa-dxz][\)\.]|$|Javob:|Жавоб:|Тўғри жавоб:|To\'g\'ri javob:)', q_text, re.DOTALL)
                
                clean_options = []
                for o in options:
                    o_clean = re.split(r'(?i)(Javob:|Жавоб:|To\'g\'ri javob:|Тўғри жавоб:)', o)[0].strip()
                    if o_clean and o_clean not in clean_options:
                        clean_options.append(o_clean)
                
                if len(clean_options) > 4:
                    clean_options = clean_options[:4]
                
                ans_match = re.search(r'(?i)(?:Javob|Жавоб|To\'g\'ri javob|Тўғри жавоб):\s*([A-DXZa-dxz])', q_text)
                if ans_match and len(clean_options) >= 2:
                    ans_letter = ans_match.group(1).upper()
                    correct_index = ord(ans_letter) - ord('A')
                    
                    if 0 <= correct_index < len(clean_options):
                        cursor.execute("INSERT INTO tests (subject, question, options, correct_index) VALUES (?, ?, ?, ?)",
                                       (current_subject, question_body, "&&".join(clean_options), correct_index))
        
        conn.commit()
        print("Word fayli muvaffaqiyatli yuklandi va haqiqiy Telegram Quiz formatiga o'tkazildi!")
    except Exception as e:
        print("Word faylini o'qishda xatolik:", e)
    finally:
        conn.close()

# START BUYRUG'I
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    conn = sqlite3.connect("quiz.db")
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT subject FROM tests")
    subjects = cursor.fetchall()
    conn.close()

    if not subjects:
        await message.answer("Bazada testlar topilmadi.")
        return

    builder = InlineKeyboardBuilder()
    for sub in subjects:
        sub_name = sub[0] # Tuple ichidan matnni ajratib olish (Xatolik tuzatilgan joyi)
        sub_id = get_subject_id(sub_name)
        builder.button(text=f"📂 {sub_name}", callback_data=f"sub_{sub_id}")
    builder.adjust(1)

    await message.answer("Assalomu alaykum! Mavzulardan birini tanlang va haqiqiy Telegram Quiz testini boshlang:", reply_markup=builder.as_markup())

# HAQIQIY TELEGRAM QUIZ JONATISH
@dp.callback_query(F.data.startswith("sub_") | F.data.startswith("nxt_"))
async def send_telegram_quiz(callback: types.CallbackQuery):
    target_sub_id = callback.data.split("_")[1]

    conn = sqlite3.connect("quiz.db")
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT subject FROM tests")
    all_subjects = cursor.fetchall()
    
    subject_name = None
    for sub in all_subjects:
        sub_name = sub[0]
        if get_subject_id(sub_name) == target_sub_id:
            subject_name = sub_name
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
            is_anonymous=False
        )
        
        builder = InlineKeyboardBuilder()
        builder.button(text="Keyingi savol ➡️", callback_data=f"nxt_{target_sub_id}")
        builder.button(text="Menu 🏠", callback_data="back_to_menu")
        builder.adjust(1)
        await callback.message.answer("Savolga javob berib, keyingisiga o'tish tugmasini bosing:", reply_markup=builder.as_markup())
        
        try:
            await callback.message.delete()
        except:
            pass
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
        sub_id = get_subject_id(sub_name)
        builder.button(text=f"📂 {sub_name}", callback_data=f"sub_{sub_id}")
    builder.adjust(1)

    await callback.message.answer("Iltimos, test yechmoqchi bo'lgan **mavzuni tanlang**:", reply_markup=builder.as_markup())
    try:
        await callback.message.delete()
    except:
        pass

async def main():
    init_db()
    import_from_word()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
