import nest_asyncio
nest_asyncio.apply()


import datetime
import json
import os
import uuid
import io
import asyncio
import os

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

# ====== الاعدادات ======

BOT_TOKEN = os.getenv("BOT_TOKEN")

  # حط ايديك هنا الاول
OWNER_ID = 5984493079 # انت - صاحب البوت
ADMINS = [] # الادمن العاديين هيتسجلوا في ملف
ADMIN_FILE = "admins.json" # ملف الادمن الجديد


DATA_FILE = "maktabtek_data.json"
BACKUP_FILE = "maktabtek_backup.json"
FILE_NAME = "maktabtek_data.json"
TELEGRAM_STORAGE_CHAT_ID = -1004325410340 # ID قناة "خاصه كتب"

data = {} # هنفضيها ونحملها من التليجرام

# حالات نشر الكتاب والتعديل والبحث
(
    SECTION,
    TITLE,
    COVER,
    DESC,
    PRICE,
    PDF,
    NEW_SECTION,
    EDIT_SELECT,
    EDIT_FIELD,
    SEARCH_TEXT,
    PROMOTE_CHANNEL,  
    PROMOTE_CONFIRM,  
    ADD_ADMIN_ID, 
    REMOVE_ADMIN_ID,
    BROADCAST,
    PROMOTE_SECTION, # حالة اختيار القسم
) = range(16)


# ====== دوال الداتا + Backup ======
def backup_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data_content = f.read()
        with open(BACKUP_FILE, "w", encoding="utf-8") as f:
            f.write(data_content)


"""def load_data():
    if not os.path.exists(DATA_FILE):
        return {
            "users": [],
            "sections": ["تطوير ذات", "برمجة"],
            "books": [],
            "banned": [],
        }
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)"""


async def save_to_telegram(context: ContextTypes.DEFAULT_TYPE):
    if not context: return # <-- ضيف السطر ده
    backup_data()
    with open(DATA_FILE, "rb") as f:
        await context.bot.send_document(
            chat_id=TELEGRAM_STORAGE_CHAT_ID,
            document=f,
            filename=FILE_NAME,
            caption=f"backup {datetime.datetime.now()}"
        )
    print("✅ تم حفظ الداتا على تليجرام")



async def load_from_telegram(app: Application):
    global data, ADMINS
    if os.path.exists(ADMIN_FILE):
        with open(ADMIN_FILE, "r") as f:
            ADMINS = json.load(f)
    try:
        async for msg in app.bot.get_chat_history(chat_id=TELEGRAM_STORAGE_CHAT_ID, limit=5):
            if msg.document and msg.document.file_name == FILE_NAME:
                file = await app.bot.get_file(msg.document.file_id)
                await file.download_to_drive(DATA_FILE)
                print("✅ تم تحميل الداتا من تليجرام")
                break
    except Exception as e:
        print(f"مفيش داتا قديمة: {e}")

    # لو مفيش ملف نعمل واحد جديد
    if not os.path.exists(DATA_FILE):
        data = {"users": [], "sections": ["تطوير ذات", "برمجة"], "books": [], "banned": [], "last_reset": str(datetime.date.today())}
    else:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

    # ====== التصفير التلقائي ======
    today = str(datetime.date.today())
    if data.get("last_reset")!= today:
        print("يوم جديد. بنصفر التحميلات...")
        for u in data["users"]:
            u["daily_downloads"] = 0 # صفر اليومي
            u["today_downloaded"] = []
            u["points"] = u.get("points",0) + 1 # بونص نقطة كل يوم
        for b in data["books"]:
            b["today_dl"] = 0 # صفر احصائيات اليوم
        data["last_reset"] = today
        await save_data(data, None) # احفظ بعد التصفير
    
async def save_data(data_obj, context: ContextTypes.DEFAULT_TYPE):
    backup_data()
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data_obj, f, ensure_ascii=False, indent=4)
    await save_to_telegram(context) # هتنادي على اللي فوقيها على طول
    
    

# ====== دوال مساعدة ======

def is_owner(user_id):
    """يرجع True لو اليوزر هو المالك صاحب البوت"""
    return user_id == OWNER_ID

def is_admin(user_id):
    """يرجع True لو اليوزر مالك او ادمن عادي"""
    return user_id == OWNER_ID or user_id in ADMINS


async def add_user(user_id, name, context):
    global data
    if not any(u["id"] == user_id for u in data["users"]):
        data["users"].append(
            {
                "id": user_id,
                "name": name,
                "fav": [],
                "join_date": str(datetime.date.today()),
                "uploads": 0,
                "downloads": 0,
                "points": 0,
                "daily_downloads": 0, # <-- ضيف ده
                "referral_code": str(uuid.uuid4())[:6].upper(),
                "referred_by": None,
                "is_vip": False, "vip_until": None
            }
        )
        await save_data(data, context)
        print(f"تم اضافة مستخدم جديد: {name}")


# ====== 1. /start ======
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    
    if context.args and context.args[0].startswith("book_"):
        book_id = context.args[0].replace("book_", "")
        book = next((b for b in data["books"] if b["id"] == book_id), None)
        if book:
            await add_user(user.id, user.first_name, context)
            await send_book_card(update, book) # نعرضله الكتاب على طول
            return
    
    if user.id in data["banned"]: # <-- ضيف ده اول سطر
        await update.message.reply_text("🚫 تم حظرك من استخدام البوت")
        return
       
    await add_user(user.id, user.first_name, context)

    if is_admin(user.id): # انت والادمن نفس القايمة
        keyboard = [
            [InlineKeyboardButton("📚 ادارة المحتوى", callback_data="ignore")],
            [InlineKeyboardButton("➕ قسم جديد", callback_data="admin_add_section"), InlineKeyboardButton("📤 نشر كتاب", callback_data="admin_add_book")],
            [InlineKeyboardButton("✏️ تعديل كتاب", callback_data="admin_edit_book"), InlineKeyboardButton("🗑️ حذف كتاب", callback_data="admin_delete_book")],
            [InlineKeyboardButton("📊 الاحصائيات", callback_data="ignore")],
            [InlineKeyboardButton("👥 المستخدمين", callback_data="admin_users"), InlineKeyboardButton("🔥 الاكثر تحميل", callback_data="admin_top")],
            [InlineKeyboardButton("📈 احصائيات اليوم", callback_data="admin_stats"), InlineKeyboardButton("🔄 تصفير اليوم", callback_data="admin_reset")],
            [InlineKeyboardButton("🏆 التوب 10", callback_data="top_users")],
        ]
        if is_owner(user.id):
        	keyboard.append([InlineKeyboardButton("👑 ادارة الادمن", callback_data="admin_manage_admins")])
        	keyboard.append([InlineKeyboardButton("📢 ارسال جماعي", callback_data="admin_broadcast")])
    else:
        user_data = next((u for u in data["users"] if u["id"] == user.id), None)
        downloads_left = 5 - user_data.get("daily_downloads", 0) # باقي كام
        
        keyboard = [
            [InlineKeyboardButton("📚 تصفح المكتبة", callback_data="ignore")],
            [InlineKeyboardButton("📖 الاقسام", callback_data="user_sections"), InlineKeyboardButton("🔍 بحث متقدم", callback_data="user_search")],
            [InlineKeyboardButton("✨ المفضلة", callback_data="user_fav"), InlineKeyboardButton("🆕 الجديد", callback_data="user_new")],
            [InlineKeyboardButton("🆓 المجاني", callback_data="filter_free"), InlineKeyboardButton("💰 المدفوع", callback_data="filter_paid")],
            [InlineKeyboardButton("📊 احصائياتي", callback_data="user_stats"), InlineKeyboardButton("🛒 المتجر", callback_data="user_shop")],
            [InlineKeyboardButton("🏆 التوب 10", callback_data="top_users")],
            [InlineKeyboardButton("👥 دعوة اصدقاء", callback_data="referral")],
            [InlineKeyboardButton("📢 قنواتنا على منصات التواصل تابعنا ليصلك كل جديد ", callback_data="my_channels")],
            [InlineKeyboardButton("📢 اربط قناتك بالبوت", callback_data="user_promote")]
        ]
        
        caption = f"👋 اهلا {user.first_name} في مكتبتك\n📥 التحميلات المتبقية اليوم: *{downloads_left}* من 5"
        await update.message.reply_text(caption, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        return # مهم عشان ميبعتش الرسالة اللي تحت

    # حرك السطر ده برا الـ if/else
    await update.message.reply_text(f"👋 اهلا {user.first_name} في مكتبتك", reply_markup=InlineKeyboardMarkup(keyboard))
# ====== 2. جزء الأدمن ======
async def admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "admin_manage_admins":
        if not is_owner(query.from_user.id): 
            await query.answer("ده للمالك بس", show_alert=True)
            return
        text = "الادمن الحاليين:\n"
        for admin_id in ADMINS:
            admin_name = next((u['name'] for u in data["users"] if u["id"] == admin_id), admin_id)
            text += f"- {admin_name} : `{admin_id}`\n"
        keyboard = [
            [InlineKeyboardButton("➕ رفع ادمن جديد", callback_data="add_admin")],
            [InlineKeyboardButton("➖ ازالة ادمن", callback_data="remove_admin")],
            [InlineKeyboardButton("⬅️ رجوع", callback_data="back_to_menu")]
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        return

    if query.data == "admin_broadcast":
        await query.edit_message_text("ابعت الرسالة اللي عايز تبعتها لكل المستخدمين")
        return BROADCAST
    
    if query.data == "add_admin":
        await query.edit_message_text("ابعتلي ايدي اليوزر اللي عايز ترفعه ادمن")
        return ADD_ADMIN_ID

    if query.data == "remove_admin":
        await query.edit_message_text("ابعتلي ايدي اليوزر اللي عايز تشيله من الادمن")
        return REMOVE_ADMIN_ID
    
    if query.data == "admin_add_section":
        await query.edit_message_text("ابعتلي اسم القسم الجديد:")
        return NEW_SECTION

    if query.data == "admin_add_book":
        return await add_book_start(update, context)

    if query.data == "admin_edit_book":
        if not data["books"]:
            await query.edit_message_text("مفيش كتب لسه")
            return ConversationHandler.END
        keyboard = [[InlineKeyboardButton(b["title"], callback_data=f"edit_{b['id']}")] for b in data["books"]]
        await query.edit_message_text("اختار الكتاب اللي عايز تعدله:", reply_markup=InlineKeyboardMarkup(keyboard))
        return EDIT_SELECT

    if query.data == "admin_delete_book":
        if not data["books"]:
            await query.edit_message_text("مفيش كتب لسه")
            return ConversationHandler.END
        keyboard = [[InlineKeyboardButton(f"🗑️ {b['title']}", callback_data=f"del_{b['id']}")] for b in data["books"]]
        await query.edit_message_text("اختار الكتاب اللي عايز تحذفه:", reply_markup=InlineKeyboardMarkup(keyboard))
        return ConversationHandler.END 
        
    if query.data == "admin_users":
        keyboard = []
        text = "المستخدمين:\n"
        for u in data["users"]:
            status = "🚫 محظور" if u["id"] in data["banned"] else "✅ شغال"
            text += f"- {u['name']} - رفع: {u.get('uploads',0)} - تحميل: {u.get('downloads',0)} - {status}\n"
            if u["id"] != OWNER_ID:
                btn_text = "فك حظر" if u["id"] in data["banned"] else "حظر"
                keyboard.append([InlineKeyboardButton(f"{btn_text} {u['name']}", callback_data=f"ban_{u['id']}")])
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        return ConversationHandler.END

    if query.data == "admin_top":
        if not data["books"]:
            await query.edit_message_text("مفيش كتب لسه")
            return ConversationHandler.END
        top_books = sorted(data["books"], key=lambda x: x.get("downloads", 0), reverse=True)[:5]
        text = "اكتر 5 كتب تحميل:\n"
        for b in top_books:
            text += f"- {b['title']} : {b.get('downloads',0)} تحميل\n" # <-- كملتها هنا
        await query.edit_message_text(text)
        return ConversationHandler.END

    if query.data == "admin_stats":
        today = str(datetime.date.today())
        new_users = len([u for u in data["users"] if u.get("join_date") == today])
        today_downloads = sum([b.get("today_dl", 0) for b in data["books"]])
        await query.edit_message_text(f"📊 احصائيات اليوم:\nمستخدمين جداد: {new_users}\nتحميلات اليوم: {today_downloads}")
        return ConversationHandler.END

    if query.data.startswith("ban_"):
        user_id = int(query.data.replace("ban_", ""))
        if user_id not in data["banned"]:
            data["banned"].append(user_id)
            await query.edit_message_text("✅ تم حظر المستخدم")
        else:
            data["banned"].remove(user_id)
            await query.edit_message_text("✅ تم فك الحظر")
        await save_data(data, context)
        return ConversationHandler.END


async def reset_today_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("جارى التصفير ....")
    
    for book in data["books"]:
        book["today_dl"] = 0
    await save_data(data, context)
    
    await query.edit_message_text("✅ تم تصفير تحميلات اليوم لكل الكتب")

async def save_new_section(update: Update, context: ContextTypes.DEFAULT_TYPE):
    section_name = update.message.text
    if section_name not in data["sections"]:
        data["sections"].append(section_name)
        await save_data(data, context)
        await update.message.reply_text(f"تم إضافة القسم '{section_name}' بنجاح ✅")
    else:
        await update.message.reply_text("القسم ده موجود بالفعل!")
    
    await start(update, context) # <-- ضيف السطر ده عشان يرجع للقايمة
    return ConversationHandler.END


# دوال تعديل الكتاب
async def select_book_to_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    book_id = query.data.replace("edit_", "") # id
    context.user_data["edit_id"] = book_id
    book = next((b for b in data["books"] if b["id"] == book_id), None)

    if not book:
        await query.message.reply_text("الكتاب اتمسح")
        return ConversationHandler.END

    keyboard = [
        [InlineKeyboardButton("العنوان", callback_data="edit_field_title")],
        [InlineKeyboardButton("الوصف", callback_data="edit_field_desc")],
        [InlineKeyboardButton("السعر", callback_data="edit_field_price")],
        [InlineKeyboardButton("القسم", callback_data="edit_field_section")],
        [InlineKeyboardButton("⬅️ رجوع", callback_data="admin_edit_book")], # <-- ضيف ده
        [InlineKeyboardButton("❌ الغاء", callback_data="cancel_conv")],
    ]
    await query.message.edit_text( # خليتها edit_text عشان متعملش رسايل
        f"بتعدل: *{book['title']}*\nهتعدل ايه؟",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    return EDIT_FIELD

async def get_new_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_value = update.message.text
    book_id = context.user_data["edit_id"]
    field = context.user_data["edit_field"]

    for book in data["books"]:
        if book["id"] == book_id:
            book[field] = new_value
            await save_data(data, context)
            await update.message.reply_text(f"✅ تم تعديل {field} بنجاح")
            return ConversationHandler.END

    await update.message.reply_text("الكتاب مش موجود")
    return ConversationHandler.END


async def edit_field(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    field = query.data.replace("edit_field_", "")
    context.user_data["edit_field"] = field

    if field == "section":
        # عدّلنا هنا: ضفنا newsec_ عشان يروح على get_section بتاع التعديل
        keyboard = [[InlineKeyboardButton(s, callback_data=f"newsec_{s}")] for s in data["sections"]]
        keyboard.append([InlineKeyboardButton("⬅️ رجوع", callback_data=f"edit_{context.user_data['edit_id']}")]) # رجوع للكتاب
        keyboard.append([InlineKeyboardButton("❌ الغاء", callback_data="cancel_conv")])
        await query.message.edit_text("اختار القسم الجديد:", reply_markup=InlineKeyboardMarkup(keyboard))
        return SECTION 
    else:
        keyboard = [[InlineKeyboardButton("⬅️ رجوع", callback_data=f"edit_{context.user_data['edit_id']}")]] # رجوع
        await query.message.edit_text(
            f"ابعت القيمة الجديدة للـ {field}", 
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return EDIT_SELECT





# نشر كتاب
async def add_book_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [[InlineKeyboardButton(s, callback_data=s)] for s in data["sections"]]
    keyboard.append([InlineKeyboardButton("❌ الغاء", callback_data="cancel_conv")])
    await query.message.reply_text(
        "اختار القسم:", reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SECTION


async def get_section(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 1. لو جاي من نشر كتاب عادي
    if update.message:
        section = update.message.text
    # 2. لو جاي من تعديل كتاب 
    else:
        section = update.callback_query.data.replace("newsec_", "")
    
    context.user_data["section"] = section
    msg = update.message or update.callback_query.message
    await msg.reply_text("تمام. ابعتلي عنوان الكتاب")
    return TITLE


async def get_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["title"] = update.message.text
    await update.message.reply_text("ابعتلي صورة الغلاف")
    return COVER


async def get_cover(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["cover"] = update.message.photo[-1].file_id
    await update.message.reply_text("ابعتلي وصف الكتاب")
    return DESC


async def get_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["desc"] = update.message.text
    keyboard = [
        [InlineKeyboardButton("مجاني", callback_data="free")],
        [InlineKeyboardButton("مدفوع", callback_data="paid")],
    ]
    await update.message.reply_text(
        "الكتاب مجاني ولا مدفوع؟", reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return PRICE


async def get_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["price"] = update.callback_query.data
    keyboard = [[InlineKeyboardButton("❌ الغاء", callback_data="cancel_conv")]]
    await update.callback_query.message.reply_text("اخر خطوة: ابعتلي ملف PDF",reply_markup=InlineKeyboardMarkup(keyboard))
   
    return PDF


async def get_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pdf_file = update.message.document.file_id
    new_book = {
        **context.user_data,
        "id": str(uuid.uuid4()),
        "pdf": pdf_file,
        "downloads": 0,
        "today_dl": 0,
        "ratings": [],
        "avg_rating": 0,
        "upload_date": str(datetime.date.today())
    }
    data["books"].append(new_book)
    await save_data(data, context)
    
    user = next((u for u in data["users"] if u["id"] == update.effective_user.id), None)
    if user:
        user["uploads"] = user.get("uploads", 0) + 1
        await save_data(data, context)

    sent_channels = 0
    sent_subscribers = 0
    
    # 1. ابعت للمشتركين في القسم بس
    for u in data["users"]:
        if "subscriptions" in u and new_book["section"] in u["subscriptions"]:
            try:
                caption = f"📢 كتاب جديد في قسم: {new_book['section']}\n\n*{new_book['title']}*\n📝 {new_book['desc']}"
                keyboard = [[InlineKeyboardButton("⬇️ الحصول على الكتاب", url=f"https://t.me/{context.bot.username}?start=book_{new_book['id']}")]]
                await context.bot.send_photo(chat_id=u["id"], photo=new_book["cover"], caption=caption, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
                sent_subscribers += 1
                await asyncio.sleep(0.05)
            except: pass
    
    # 2. ابعت للقنوات اللي ضايفة القسم بس
    if "promotions" in data:
        channels_to_send = [
            p for p in data["promotions"]
            if p.get("status") == "approved" and new_book["section"] in p.get("sections", [])
        ]
        for promo in channels_to_send:
            try:
                caption = f"📚 كتاب جديد من قسم: {new_book['section']}\n\n*{new_book['title']}*\n📝 {new_book['desc']}"
                keyboard = [[InlineKeyboardButton("⬇️ الحصول على الكتاب", url=f"https://t.me/{context.bot.username}?start=book_{new_book['id']}")]]
                await context.bot.send_photo(
                    chat_id=promo["channel"],
                    photo=new_book["cover"],
                    caption=caption,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode="Markdown"
                )
                sent_channels += 1
                await asyncio.sleep(2)
            except Exception as e:
                print(f"فشل الارسال لقناة {promo['channel']}: {e}")

    # 3. رسالة للادمن
    await update.message.reply_text(f"تم نشر الكتاب بنجاح ✅\nوصل لـ {sent_subscribers} مشترك و {sent_channels} قناة في قسم {new_book['section']}")
    return ConversationHandler.END



# ====== 3. جزء المستخدم ======
async def user_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_data = next((u for u in data["users"] if u["id"] == query.from_user.id), None)

    if query.data == "user_sections":
        keyboard = [[InlineKeyboardButton(s, callback_data=f"sec_{s}")] for s in data["sections"]]
        await query.message.reply_text("اختار قسم:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data == "user_search":
        await query.message.reply_text("ابعتلي اسم الكتاب اللي بتدور عليه")
        return SEARCH_TEXT

    elif query.data == "user_fav":
        user = next((u for u in data["users"] if u["id"] == query.from_user.id), None)
        if not user: # ضيف ده
            await query.message.reply_text("حصل خطأ. ارجع للقائمة")
            return
        fav_books = [b for b in data["books"] if b["id"] in user["fav"]]
        if not fav_books:
            await query.message.reply_text("مفيش كتب في المفضله")
        else:
            await send_books_page(query, fav_books, page=0, context_data="fav")

    elif query.data == "user_new":
        new_books = data["books"][-10:] 
        new_books.reverse()
        if not new_books:
            await query.message.reply_text("مفيش كتب لسه")
        else:
            await query.message.reply_text("📚 اخر الكتب اللي اتضافت:")
            await send_books_page(query, new_books, page=0, context_data="new") 
     
    elif query.data == "filter_free":
        books = [b for b in data["books"] if b["price"] == "free"]
        await send_books_page(query, books, page=0, context_data="filter_free")
        return # ضيف ده
    elif query.data == "filter_paid":
        books = [b for b in data["books"] if b["price"] == "paid"]
        await send_books_page(query, books, page=0, context_data="filter_paid")
        return # ضيف ده
     
    elif query.data.startswith("sec_"):
        section = query.data.replace("sec_", "")
        books = [b for b in data["books"] if b["section"] == section]
        
        user_id = query.from_user.id
        user_data = next((u for u in data["users"] if u["id"] == user_id), None)
        is_subscribed = user_data and "subscriptions" in user_data and section in user_data["subscriptions"]

        # زرار المتابعة
        if is_subscribed:
            follow_btn = InlineKeyboardButton("🔕 الغاء متابعة القسم", callback_data=f"unfollow_{section}")
        else:
            follow_btn = InlineKeyboardButton("🔔 متابعة القسم", callback_data=f"follow_{section}")

        if not books:
            keyboard = [[follow_btn], [InlineKeyboardButton("⬅️ الرجوع", callback_data="user_sections")]]
            await query.message.reply_text(f"مفيش كتب في قسم {section} لسه", reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await send_books_page(query, books, page=0, context_data=f"sec_{section}")
            # بعد ما نعرض الكتب نبعت زرار المتابعة في رسالة لوحده
            keyboard = [[follow_btn], [InlineKeyboardButton("⬅️ الرجوع", callback_data="user_sections")]]
            await query.message.reply_text(f"📚 قسم: {section}", reply_markup=InlineKeyboardMarkup(keyboard))
    
    elif query.data.startswith("fav_"):
        book_id = query.data.replace("fav_", "")
        book = next((b for b in data["books"] if b["id"] == book_id), None)
        user = next((u for u in data["users"] if u["id"] == query.from_user.id), None)
        if not book:
            await query.answer("الكتاب اتمسح")
            return
        if user and book_id not in user["fav"]:
            user["fav"].append(book_id) # بنخزن id
            await save_data(data, context)
            await query.answer(f"تم اضافة '{book['title']}' للمفضلة ❤️")
        else:
            await query.answer("الكتاب ده في المفضلة اصلا")
    elif query.data.startswith("unfav_"):
        book_id = query.data.replace("unfav_", "")
        book = next((b for b in data["books"] if b["id"] == book_id), None)
        user = next((u for u in data["users"] if u["id"] == query.from_user.id), None)
        if user and book_id in user["fav"]:
            user["fav"].remove(book_id) # بنشيل id
            await save_data(data, context)
            await query.answer(f"تم الحذف من المفضلة 💔")
        else:
            await query.answer("الكتاب مش في المفضلة")
            return
    
        
    downloads_left = 5 - user_data.get("daily_downloads", 0)
    
    keyboard = [
        [InlineKeyboardButton("📚 تصفح المكتبة", callback_data="ignore")],
        [InlineKeyboardButton("📖 الاقسام", callback_data="user_sections"), InlineKeyboardButton("🔍 بحث متقدم", callback_data="user_search")],
        [InlineKeyboardButton("✨ المفضلة", callback_data="user_fav"), InlineKeyboardButton("🆕 الجديد", callback_data="user_new")],
        [InlineKeyboardButton("🆓 المجاني", callback_data="filter_free"), InlineKeyboardButton("💰 المدفوع", callback_data="filter_paid")],
        [InlineKeyboardButton("📊 احصائياتي", callback_data="user_stats"), InlineKeyboardButton("🛒 المتجر", callback_data="user_shop")],
        [InlineKeyboardButton("🏆 التوب 10", callback_data="top_users")],
        [InlineKeyboardButton("👥 دعوة اصدقاء", callback_data="referral")],
        [InlineKeyboardButton("📢 قنواتي وحساباتي", callback_data="my_channels")],
        [InlineKeyboardButton("📢 اربط قناتك بالبوت", callback_data="user_promote")]
    ]
    
    caption = f"👋 اهلا {query.from_user.first_name} في مكتبتك\n📥 التحميلات المتبقية اليوم: *{downloads_left}* من 5"
    await query.message.reply_text(caption, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")



async def follow_section(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    section = query.data.replace("follow_", "")
    user_id = query.from_user.id

    user_data = next((u for u in data["users"] if u["id"] == user_id), None)
    if "subscriptions" not in user_data:
        user_data["subscriptions"] = []

    if section not in user_data["subscriptions"]:
        user_data["subscriptions"].append(section)
        await save_data(data, context)
        await query.answer(f"✅ تمت متابعة قسم {section}", show_alert=True)
    else:
        await query.answer("انت متابع القسم ده خلاص")

async def unfollow_section(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    section = query.data.replace("unfollow_", "")
    user_id = query.from_user.id

    user_data = next((u for u in data["users"] if u["id"] == user_id), None)
    if "subscriptions" in user_data and section in user_data["subscriptions"]:
        user_data["subscriptions"].remove(section)
        await save_data(data, context)
        await query.answer(f"✅ تم الغاء متابعة قسم {section}", show_alert=True)
    else:
        await query.answer("انت مش متابع القسم ده")


async def user_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = next((u for u in data["users"] if u["id"] == query.from_user.id), None)
    if not user: return

    downloads_left = 5 - user.get("daily_downloads", 0)
    text = f"📊 احصائياتك يا {user['name']}\n\n"
    text += f"📅 تاريخ الانضمام: {user['join_date']}\n"
    text += f"📤 كتب رفعتها: {user.get('uploads',0)}\n"
    text += f"📥 كتب حملتها: {user.get('downloads',0)}\n"
    text += f"💎 النقاط: {user.get('points',0)} نقطة\n"  # <-- حطها هنا
    text += f"📥 متبقي اليوم: {downloads_left} من 5\n"
    text += f"❤️ المفضلة: {len(user.get('fav',[]))} كتاب"

    await query.message.reply_text(text)



async def search_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.lower()
    
    results = []
    for book in data["books"]:
        # ابحث في الاسم والوصف والقسم
        if (text in book["title"].lower() or 
            text in book["desc"].lower() or 
            text in book["section"].lower() or
            text in book["price"].lower()):
            results.append(book)
    
    if not results:
        await update.message.reply_text("مفيش نتائج 😢 جرب كلمة تانية")
    else:
        await update.message.reply_text(f"📚 لقيت {len(results)} نتيجة للبحث عن: {text}")
        await send_books_page(update, results, page=0, context_data=f"search_{text}")
    return ConversationHandler.END


async def back_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await start(update, context) # نرجع للستارت


async def user_promote_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text(
        "عشان اخدمك في قناتك لازم تخليني ادمن 📢\n\n"
        "**الخطوات:**\n"
        "1. ادخل القناة بتاعتك\n"
        "2. ادخل على الاعدادات > المسؤولين\n"
        "3 . اضغط 'اضافة مسؤول' وابحث عن البوت: `@Maktaptk_bot`\n"
        "4. اديني صلاحية 'نشر الرسائل' فقط\n"
        "بعد ما تخليني ادمن ابعتلي يوزر القناة زي كده: `@اسم_القناة`"
    )
    return PROMOTE_CHANNEL


async def get_channel_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    channel = update.message.text.strip()
    context.user_data["promo_channel"] = channel
    context.user_data["promo_sections"] = [] # هنخزن الاقسام هنا

    keyboard = [[InlineKeyboardButton(s, callback_data=f"promosec_{s}")] for s in data["sections"]]
    keyboard.append([InlineKeyboardButton("✅ تم اخترت الاقسام", callback_data="promosec_done")])
    keyboard.append([InlineKeyboardButton("❌ الغاء", callback_data="cancel_conv")])
    
    await update.message.reply_text(
        "اختار الاقسام اللي عايز الكتب تنزل عندك. دوس على القسم عشان تضيفه\n"
        "ولما تخلص دوس 'تم اخترت الاقسام'",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return PROMOTE_SECTION

async def select_promo_section(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data_cb = query.data

    if data_cb == "promosec_done":
        if not context.user_data["promo_sections"]:
            await query.message.reply_text("لازم تختار قسم واحد على الاقل")
            return PROMOTE_SECTION
        await query.message.reply_text("تمام كده. اكتب 'تم' للتأكيد النهائي")
        return PROMOTE_CONFIRM
    
    section = data_cb.replace("promosec_", "")
    if section not in context.user_data["promo_sections"]:
        context.user_data["promo_sections"].append(section)
        await query.answer(f"تم اضافة {section} ✅")
    else:
        context.user_data["promo_sections"].remove(section)
        await query.answer(f"تم حذف {section} ❌")
    
    # نحدث الرسالة ونعلم على اللي اختاره
    keyboard = []
    for s in data["sections"]:
        btn = f"✅ {s}" if s in context.user_data["promo_sections"] else s
        keyboard.append([InlineKeyboardButton(btn, callback_data=f"promosec_{s}")])
    keyboard.append([InlineKeyboardButton("✅ تم اخترت الاقسام", callback_data="promosec_done")])
    await query.message.edit_reply_markup(InlineKeyboardMarkup(keyboard))

async def confirm_promote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text.lower() == "تم":
        user_id = update.effective_user.id
        channel = context.user_data["promo_channel"]
        sections = context.user_data["promo_sections"] # <-- الاقسام اللي اختارها

        try:
            bot_member = await context.bot.get_chat_member(chat_id=channel, user_id=context.bot.id)
            if bot_member.status not in ["administrator", "creator"]:
                await update.message.reply_text("❌ انا مش ادمن لسه. اتأكد واديني صلاحية النشر وبعدين اكتب تم")
                return PROMOTE_CONFIRM
        except Exception:
            await update.message.reply_text("❌ مقدرتش اوصل للقناة. اتأكد انك كاتب @صح وانا ادمن")
            return PROMOTE_CONFIRM

        if "promotions" not in data:
            data["promotions"] = []

        data["promotions"].append({
            "user_id": user_id,
            "user_name": update.effective_user.first_name,
            "channel": channel,
            "sections": sections, # <-- خزناها ليست
            "status": "pending",
            "date": str(datetime.date.today())
        })
        await save_data(data, context)

        # نبلغ الادمن
        for admin_id in [OWNER_ID] + ADMINS:
            try:
                keyboard = [
                    [InlineKeyboardButton("✅ موافقة", callback_data=f"approve_{user_id}")],
                    [InlineKeyboardButton("❌ رفض", callback_data=f"reject_{user_id}")]
                ]
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=f"📢 طلب جديد لربط قناة\n\nالاسم: {update.effective_user.first_name}\nID: {user_id}\nالقناة: {channel}\nالاقسام: {', '.join(sections)}",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            except: pass

        await update.message.reply_text(f"✅ تم ارسال طلبك للادمن. هيتم مشاركه الكتب الجديده في قناتك تلقائيا في الاقسام: {', '.join(sections)}")
    else:
        await update.message.reply_text("تم الالغاء")
    return ConversationHandler.END



#داله عرض الكتاب في البوت 
async def send_book_card(update_obj, book):
    avg = book.get("avg_rating", 0)
    stars = "⭐" * round(avg) + "☆" * (5 - round(avg))
    price_text = "🆓 مجاني" if book['price']=='free' else f"💰 مدفوع"
    
    keyboard = [
        [
            InlineKeyboardButton("⬇️ تحميل", callback_data=f"dl_{book['id']}"),
            InlineKeyboardButton("📖 قراءة اونلاين", callback_data=f"read_{book['id']}"),
        ],
        [
            InlineKeyboardButton("❤️ اضافة للمفضلة", callback_data=f"fav_{book['id']}"),
            InlineKeyboardButton("💔 حذف من المفضلة", callback_data=f"unfav_{book['id']}")
        ],
        [InlineKeyboardButton("⬅️ رجوع للقائمة", callback_data="back_to_menu")]
    ]
    target = update_obj.message if hasattr(update_obj, "message") else update_obj.callback_query.message
    await target.reply_photo(
        photo=book["cover"],
        caption=f"📖 *{book['title']}*\n\n📝 {book['desc']}\n\nالحالة: {price_text}\n📥 التحميلات: {book.get('downloads',0)}\nالتقييم: {stars} `{avg}/5`",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )

BOOKS_PER_PAGE = 5 # عدد الكتب في الصفحه

async def send_books_page(update_obj, books, page=0, context_data="all"):
    start = page * BOOKS_PER_PAGE
    end = start + BOOKS_PER_PAGE
    page_books = books[start:end]
    total_pages = (len(books) -1)//BOOKS_PER_PAGE + 1

    if not page_books:
        target = update_obj.message if hasattr(update_obj, "message") else update_obj.callback_query.message
        await target.reply_text("مفيش كتب في الصفحه دي")
        return

    for book in page_books:
        await send_book_card(update_obj, book)

    # ازرار التنقل ب ارقام
    keyboard = []
    nav_buttons = []

    # نعرض 3 ارقام حوالين الصفحه الحاليه
    for p in range(max(0, page-1), min(total_pages, page+2)):
        btn_text = f"[{p+1}]" if p == page else str(p+1) # الصفحه الحاليه بين []
        nav_buttons.append(InlineKeyboardButton(btn_text, callback_data=f"page_{context_data}_{p}"))

    keyboard.append(nav_buttons)

    if start > 0:
        keyboard[0].insert(0, InlineKeyboardButton("⬅️", callback_data=f"page_{context_data}_{page-1}"))
    if end < len(books):
        keyboard[0].append(InlineKeyboardButton("➡️", callback_data=f"page_{context_data}_{page+1}"))

    keyboard.append([InlineKeyboardButton("⬅️ رجوع للقائمة", callback_data="back_to_menu")])

    target = update_obj.message if hasattr(update_obj, "message") else update_obj.callback_query.message
    await target.reply_text(
        f"📄 صفحه {page + 1} من {total_pages} | 📚 اجمالي: {len(books)} كتاب",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
async def handle_page(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    parts = query.data.split("_", 2) # نقسم ل 3 اجزاء بس: page_context_pageNum
    if len(parts) != 3:
        await query.message.reply_text("حصل خطأ. ارجع للقائمة")
        return
        
    _, context_data, page = parts
    page = int(page)
    
    if context_data.startswith("sec_"):
        section = context_data.replace("sec_", "")
        books = [b for b in data["books"] if b["section"] == section]
        await send_books_page(query, books, page, context_data)
        
    elif context_data == "fav":
        user = next((u for u in data["users"] if u["id"] == query.from_user.id), None)
        if not user:
            await query.message.reply_text("حصل خطأ. ارجع للقائمة")
            return
        books = [b for b in data["books"] if b["id"] in user["fav"]]
        await send_books_page(query, books, page, context_data)
        
    elif context_data == "new":
        books = data["books"][-10:]
        books.reverse()
        await send_books_page(query, books, page, context_data)
        
    elif context_data.startswith("search_"):
        text = context_data.replace("search_", "")
        books = [b for b in data["books"] if text.lower() in b["title"].lower() or text.lower() in b["desc"].lower()]
        await send_books_page(query, books, page, context_data)
    
    elif context_data.startswith("filter_"):
        price = context_data.replace("filter_", "")
        books = [b for b in data["books"] if b["price"] == price]
        await send_books_page(query, books, page, context_data)
        
    else:
        await query.message.reply_text("القسم ده مش موجود")

async def handle_rate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, book_id, rating = query.data.split("_") # id
    rating = int(rating)
    book = next((b for b in data["books"] if b["id"] == book_id), None) # id
    
    if not book:
        await query.message.reply_text("الكتاب اتمسح")
        return
        
    user_id = query.from_user.id
    book["ratings"] = [r for r in book["ratings"] if r["user"] != user_id] # امسح القديم
    book["ratings"].append({"user": user_id, "rate": rating}) # ضيف الجديد
    book["avg_rating"] = round(sum(r["rate"] for r in book["ratings"]) / len(book["ratings"]), 1) # المتوسط
    await save_data(data, context)
    await query.message.reply_text(f"شكرا لتقييمك: {rating} ⭐")


async def handle_download(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("جارى التحميل ")
    book_id = query.data.split("_", 1)[1]
    book = next((b for b in data["books"] if b["id"] == book_id), None)
    user = next((u for u in data["users"] if u["id"] == query.from_user.id), None)

    if not book:
        await query.message.reply_text("الكتاب اتمسح")
        return
    if not user:
        await query.message.reply_text("حصل خطأ. اعمل /start")
        return

    # ====== 1. شيك على التحميلات اليومية ======
    MAX_DAILY = 5
    is_vip = user.get("is_vip", False) and user.get("vip_until", "2000-01-01") >= str(datetime.date.today())
    if not is_admin(query.from_user.id) and not is_vip:
        if user.get("daily_downloads", 0) >= MAX_DAILY:
            await query.message.reply_text(f"⚠️ خلصت 5 تحميلات اليوم.\nاشترك VIP من /vip عشان تحميل بلا حدود")
            return

    # ====== 2. شيك لو الكتاب مدفوع ======
    if book["price"] == "paid":
        await query.message.reply_text("⚠️ الكتاب ده مدفوع. تواصل مع الادمن عشان تشتريه.")
        return

    # ====== 3. نزود العداد مرة واحدة بس ======
    book["downloads"] = book.get("downloads", 0) + 1
    book["today_dl"] = book.get("today_dl", 0) + 1
    user["downloads"] = user.get("downloads", 0) + 1
    user["daily_downloads"] = user.get("daily_downloads", 0) + 1
    user["points"] = user.get("points", 0) + 1
    downloads_left = MAX_DAILY - user["daily_downloads"]

    await save_data(data, context)

    # ====== 4. نبعت الملف مرة واحدة بس ======
    try:
        await context.bot.send_document(
            chat_id=query.from_user.id,
            document=book["pdf"],
            caption=f"📖 {book['title']}"
        )
        await query.message.reply_text(
            f"✅ تم التحميل بنجاح\n"
            f"📥 باقي لك {downloads_left} تحميلات اليوم\n"
            f"💎 +1 نقطة. رصيدك: {user['points']}"
        )
    except Exception as e:
        await query.message.reply_text(f"❌ مقدرتش ابعتلك الملف. ابعتلي /start")
        print(e)
        return

    # ====== 5. اسئلة التقييم ======
    keyboard = [
        [
            InlineKeyboardButton("1 ⭐", callback_data=f"rate_{book['id']}_1"),
            InlineKeyboardButton("2 ⭐", callback_data=f"rate_{book['id']}_2"),
            InlineKeyboardButton("3 ⭐", callback_data=f"rate_{book['id']}_3"),
            InlineKeyboardButton("4 ⭐", callback_data=f"rate_{book['id']}_4"),
            InlineKeyboardButton("5 ⭐", callback_data=f"rate_{book['id']}_5")
        ]
    ]
    await query.message.reply_text("عجبك الكتاب؟ قيمه من 5 ⭐", reply_markup=InlineKeyboardMarkup(keyboard))


async def handle_read(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("جارى فتح الكتاب....")
    book_id = query.data.split("_", 1)[1] # id
    book = next((b for b in data["books"] if b["id"] == book_id), None) # id

    if not book:
        await query.message.reply_text("الكتاب اتمسح")
        return

    # حاليا هنبعت الـ PDF عشان القراءة المباشرة لسه
    await context.bot.send_document(query.from_user.id, document=book["pdf"], caption=f"📖 قراءة: {book['title']}")

async def handle_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "del_confirm":
        book_id = context.user_data["del_id"]
        data["books"] = [b for b in data["books"] if b["id"] != book_id]
        await save_data(data, context)
        await query.message.reply_text("✅ تم الحذف بنجاح")
        return
        
    book_id = query.data.replace("del_", "")
    context.user_data["del_id"] = book_id
    book = next((b for b in data["books"] if b["id"] == book_id), None)
    
    keyboard = [
        [InlineKeyboardButton("✅ اه امسحه", callback_data="del_confirm")],
        [InlineKeyboardButton("❌ لا تراجع", callback_data="back_to_menu")]
    ]
    await query.message.reply_text(
        f"متأكد عايز تحذف *{book['title']}* ؟", 
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )


async def add_admin_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global ADMINS
    try:
        new_admin_id = int(update.message.text)
        if new_admin_id not in ADMINS and new_admin_id != OWNER_ID:
            ADMINS.append(new_admin_id)
            with open(ADMIN_FILE, "w") as f: json.dump(ADMINS, f)
            await update.message.reply_text(f"✅ تم رفع {new_admin_id} ادمن بنجاح")
        else: await update.message.reply_text("هو ادمن اصلا")
    except: await update.message.reply_text("ابعت رقم صحيح")
    return ConversationHandler.END

async def remove_admin_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global ADMINS
    try:
        rem_admin_id = int(update.message.text)
        if rem_admin_id in ADMINS:
            ADMINS.remove(rem_admin_id)
            with open(ADMIN_FILE, "w") as f: json.dump(ADMINS, f)
            await update.message.reply_text(f"✅ تم ازالة {rem_admin_id} من الادمن")
        else: await update.message.reply_text("مش ادمن")
    except: await update.message.reply_text("ابعت رقم صحيح")
    return ConversationHandler.END


async def broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sent = 0
    for u in data["users"]:
        try:
            await context.bot.send_message(chat_id=u["id"], text=f"📢 رسالة من الادارة:\n\n{update.message.text}")
            sent += 1
        except: pass
    await update.message.reply_text(f"✅ تم الارسال لـ {sent} مستخدم")
    return ConversationHandler.END


async def user_shop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = next((u for u in data["users"] if u["id"] == query.from_user.id), None)
    
    keyboard = [
        [InlineKeyboardButton("💎 شراء 1 تحميل اضافي = 10 نقاط", callback_data="buy_1_dl")],
        [InlineKeyboardButton("💎 شراء 3 تحميلات = 25 نقطة", callback_data="buy_3_dl")],
        [InlineKeyboardButton("⬅️ رجوع", callback_data="back_to_menu")]
    ]
    text = f"🛒 المتجر\nرصيدك: {user.get('points',0)} نقطة"
    await query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def approve_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        await query.message.reply_text("🚫 ده للادمن بس")
        return

    user_id = int(query.data.split("_")[1])

    for p in data.get("promotions", []):
        if p["user_id"] == user_id and p["status"] == "pending":
            p["status"] = "approved"
            # نفعلها عند اليوزر
            user = next((u for u in data["users"] if u["id"] == user_id), None)
            if user:
                user["promo_channel"] = p["channel"]
            await save_data(data, context)

            await query.message.edit_text(f"✅ تمت الموافقة على قناة: {p['channel']}")
            # نبلغ اليوزر
            await context.bot.send_message(chat_id=user_id, text=f"🎉 تمت الموافقة! قناتك {p['channel']} اتربطت بنجاح")
            return

    await query.message.edit_text("❌ الطلب ده اتنفذ خلاص")


async def my_channels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    text = "📢 تابع صاحب البوت على:\n\n"
    text += "متنساش تعمل شير للبوت لاصحابك ❤️"
    
    keyboard = [
        [InlineKeyboardButton("📢 قناة التليجرام", url="https://t.me/cofee_cood")],
        [InlineKeyboardButton("▶️ قناة اليوتيوب", url="https://youtube.com/@code_coffee1?si=Ywtt2wrYrRvh7W-o")],
        [InlineKeyboardButton("💬 قناه الواتساب", url="https://whatsapp.com/channel/0029Vb81XjoHrDZgKQ98rh2J")],
        [InlineKeyboardButton("📘 صفحة الفيسبوك", url="https://www.facebook.com/profile.php?id=61591861586791")],
        [InlineKeyboardButton("📷 الانستجرام", url="https://instagram.com/")], # حط لينكك هنا
        [InlineKeyboardButton("⬅️ رجوع للقائمة", callback_data="back_to_menu")]
    ]
    await query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def reject_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = int(query.data.split("_")[1])
    await query.message.edit_text(f"❌ تم رفض الطلب")
    await context.bot.send_message(chat_id=user_id, text="❌ تم رفض طلب ربط القناة")

async def buy_item(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = next((u for u in data["users"] if u["id"] == query.from_user.id), None)
    
    if query.data == "buy_1_dl":
        price, dl = 10, 1
    elif query.data == "buy_3_dl":
        price, dl = 25, 3
    else: return

    if user.get("points",0) >= price:
        user["points"] -= price
        user["daily_downloads"] = user.get("daily_downloads",0) - dl # بنقص عشان نزود
        if user["daily_downloads"] < 0: user["daily_downloads"] = 0
        await save_data(data, context)
        await query.message.reply_text(f"✅ تم شراء {dl} تحميل بنجاح")
    else:
        await query.message.reply_text("❌ معندكش نقاط كفاية")

async def top_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    top = sorted(data["users"], key=lambda x: x.get("downloads",0), reverse=True)[:10]
    
    text = "🏆 توب 10 اكتر ناس بتحمل\n"
    for i, u in enumerate(top, 1):
        text += f"{i}. {u['name']} - {u.get('downloads',0)} تحميل\n"
    await query.message.reply_text(text)


async def referral_system(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = next((u for u in data["users"] if u["id"] == query.from_user.id), None)
    text = f"👥 نظام الدعوات\n"
    text += f"كود الدعوة بتاعك: `{user['referral_code']}`\n"
    text += f"ابعته لصاحبك. اول ما يسجل بيه هتاخد 2 تحميل اضافي فوراً"
    await query.message.reply_text(text, parse_mode="Markdown")

async def vip_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("💎 اشتراك VIP\n30 يوم بلا حدود تحميل\nالسعر: 50 جنيه\nحول  كاش \nرقم الكاش :- +201115171120\nوبعدين ابعت سكرين للادمن")
    
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        await query.message.edit_text("تم الالغاء ❌")
        await start(update, context)
    else:
        await update.message.reply_text("تم الالغاء ❌")
    return ConversationHandler.END
   
# ====== التشغيل ======
async def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    await load_from_telegram(app)

    conv_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(admin_menu, pattern="^admin_add_section$"),
            CallbackQueryHandler(add_book_start, pattern="^admin_add_book$"),
            CallbackQueryHandler(admin_menu, pattern="^admin_edit_book$"),
            CallbackQueryHandler(admin_menu, pattern="^admin_manage_admins$"),
            CallbackQueryHandler(admin_menu, pattern="^add_admin$"),
            CallbackQueryHandler(admin_menu, pattern="^remove_admin$"),
            CallbackQueryHandler(user_promote_start, pattern="^user_promote$"),
            CallbackQueryHandler(user_menu, pattern="^user_search$"),
        ],
        states={
        PROMOTE_CHANNEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_channel_link)],
        PROMOTE_SECTION: [CallbackQueryHandler(select_promo_section)],
        PROMOTE_CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_promote)],
        NEW_SECTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_new_section)],
        SECTION: [MessageHandler(filters.TEXT, get_section), CallbackQueryHandler(get_section)],
        TITLE: [MessageHandler(filters.TEXT, get_title)],
        COVER: [MessageHandler(filters.PHOTO, get_cover)],
        DESC: [MessageHandler(filters.TEXT, get_desc)],
        PRICE: [CallbackQueryHandler(get_price)],
        PDF: [MessageHandler(filters.Document.PDF, get_pdf)],
        EDIT_SELECT: [CallbackQueryHandler(select_book_to_edit), MessageHandler(filters.TEXT, get_new_value)],
        EDIT_FIELD: [CallbackQueryHandler(edit_field)],
        SEARCH_TEXT: [MessageHandler(filters.TEXT, search_text)],
        ADD_ADMIN_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_admin_id)],
        REMOVE_ADMIN_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, remove_admin_id)],
        BROADCAST: [MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_message)], # <-- دخله هنا
    },
    fallbacks=[CommandHandler("cancel", cancel)],
)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(lambda u,c: u.callback_query.answer(), pattern="^ignore$"))
    app.add_handler(CallbackQueryHandler(user_shop, pattern="^user_shop$"))
    app.add_handler(CallbackQueryHandler(user_stats, pattern="^user_stats$"))
    app.add_handler(CallbackQueryHandler(user_menu, pattern="^filter_free$"))  # دول تبع user_menu
    app.add_handler(CallbackQueryHandler(user_menu, pattern="^filter_paid$"))
    app.add_handler(CallbackQueryHandler(user_menu, pattern="^sec_|^fav_|^unfav_|^user_|^back_to_menu$"))
    app.add_handler(CallbackQueryHandler(handle_download, pattern="^dl_"))
    app.add_handler(CallbackQueryHandler(handle_read, pattern="^read_"))
    app.add_handler(CallbackQueryHandler(handle_delete, pattern="^del_"))
    app.add_handler(CallbackQueryHandler(handle_page, pattern="^page_"))
    app.add_handler(CallbackQueryHandler(handle_rate, pattern="^rate_"))
    app.add_handler(CallbackQueryHandler(reset_today_stats, pattern="^admin_reset$"))
    app.add_handler(CallbackQueryHandler(select_book_to_edit, pattern="^edit_"))
    app.add_handler(CallbackQueryHandler(cancel, pattern="^cancel_conv$"))
    
    app.add_handler(CallbackQueryHandler(buy_item, pattern="^buy_"))
    app.add_handler(CallbackQueryHandler(top_users, pattern="^top_users$"))
    app.add_handler(CallbackQueryHandler(referral_system, pattern="^referral$"))
    app.add_handler(CommandHandler("vip", vip_command))
    app.add_handler(CallbackQueryHandler(my_channels, pattern="^my_channels$"))
    app.add_handler(CallbackQueryHandler(approve_callback, pattern="^approve_"))
    app.add_handler(CallbackQueryHandler(reject_callback, pattern="^reject_"))
    app.add_handler(CallbackQueryHandler(follow_section, pattern="^follow_"))
    app.add_handler(CallbackQueryHandler(unfollow_section, pattern="^unfollow_"))
    app.add_handler(CallbackQueryHandler(back_to_menu, pattern="^back_to_menu$"))
    app.add_handler(CallbackQueryHandler(get_section, pattern="^newsec_"))
   

    print("البوت اشتغل")
    await app.run_polling()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main()) 
