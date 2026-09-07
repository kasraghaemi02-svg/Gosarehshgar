from __future__ import annotations

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery


def _contact_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 تماس با پشتیبانی واتساپ", url=CONTACT_LINK)]
    ])

from . import db
from .keyboards import (
    kb_admin_main,
    kb_agency_main,
    kb_direct_client_main,
    kb_request_contact,
    kb_back_main,
)
from .states import Onboarding

router = Router()
BRAND_NAME = "ایران آوسبیلدونگ"
CONTACT_LINK = "https://wa.me/message/2N2G7P6T3V7TB1"


def _menu_for_role(role: str, db_path: str = None, user_id: int = None):
    if role in ("super_admin", "admin"):
        perms = None
        if role == "admin" and db_path and user_id:
            perms = db.get_admin_permissions(db_path, user_id)
        return kb_admin_main(role=role, perms=perms)
    if role == "agency":
        return kb_agency_main()
    return kb_direct_client_main()


@router.message(CommandStart())
async def start_cmd(message: Message, state: FSMContext, cfg, db_path: str):
    user_id = message.from_user.id
    print(f"DEBUG: /start triggered by user {user_id} in handlers_start.py")
    
    if user_id == cfg.super_admin_id:
        db.upsert_user_on_license_join(
            db_path=db_path,
            user_id=user_id,
            role="super_admin",
            full_name=message.from_user.full_name,
            license_code="",
        )
        await message.answer(f"✨ {BRAND_NAME}\n\n🛠️ پنل مدیریت\n\nبه سیستم خوش اومدی! 👋", reply_markup=kb_admin_main())
        await state.clear()
        return

    user = db.get_user(db_path, user_id)

    # ادمین‌هایی که از پنل اضافه شدند (phone_verified ممکنه 0 باشه)
    if user and user["role"] in ("admin", "super_admin"):
        name = user.get("full_name", "ادمین عزیز")
        await message.answer(
            f"✨ {BRAND_NAME}\n\n🛠️ پنل مدیریت\n\nسلام {name}! خوش اومدی 👋",
            reply_markup=_menu_for_role(user["role"], db_path, user_id)
        )
        await state.clear()
        return

    if user and user.get("is_phone_verified") == 1:
        name = user.get("full_name", "دوست عزیز")
        lic_code = user.get("license_code")
        lic = db.get_license(db_path, lic_code) if lic_code else None
        
        # اگر کاربر لایسنس ندارد یا لایسنس او پیدا نشد (حذف شده)
        if not lic_code or not lic:
            await message.answer(
                f"✨ {BRAND_NAME}\n\n"
                "⚠️ متاسفانه لایسنس فعالی برای شما یافت نشد.\n\n"
                "💡 اگر کد لایسنس جدید دارید، آن را وارد کنید یا جهت بررسی موضوع، یک تیکت ثبت کنید.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔑 وارد کردن کد لایسنس", callback_data="enter_manual_license")],
                    [InlineKeyboardButton(text="🎫 ثبت تیکت", callback_data="create_new_ticket")],
                    [InlineKeyboardButton(text="💬 تماس با پشتیبانی", url=CONTACT_LINK)]
                ])
            )
            return
        
        if lic.is_active != 1:
            await message.answer(
                f"⚠️ لایسنس شما ({lic_code}) در حال حاضر غیرفعال است.\n\n"
                "شما فقط به بخش تیکت‌ها دسترسی دارید یا می‌توانید با مدیریت تماس بگیرید.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🎫 تیکت‌ها", callback_data="view_my_tickets")],
                    [InlineKeyboardButton(text="💬 تماس با پشتیبانی", url=CONTACT_LINK)]
                ])
            )
            return

        if user["role"] == "agency":
            name = lic.agency_name if lic else name
            await message.answer(f"✨ {BRAND_NAME}\n\nسلام {name}! 🏢\n\nخوش اومدی! امیدوارم روزت عالی باشه 👋", reply_markup=_menu_for_role(user["role"], db_path, user_id))
        elif user["role"] == "blogger":
            await message.answer(f"✨ {BRAND_NAME}\n\nسلام همکار گرامی! 🤳\n\nخوش اومدی! امیدوارم روزت عالی باشه 👋", reply_markup=_menu_for_role(user["role"], db_path, user_id))
        else:
            await message.answer(f"✨ {BRAND_NAME}\n\nسلام {name}! 🌸\n\nخوش اومدی! امیدوارم همه چیز عالی پیش بره 👋", reply_markup=_menu_for_role(user["role"], db_path, user_id))
        await state.clear()
        return

    await message.answer(
        f"✨ {BRAND_NAME}\n\nکد لایسنس رو وارد کن:\n\n💡 اگه تو لایسنست مشکل داری یا کد دریافت نکردی، از دکمه پایین به مدیریت در واتساپ پیام بده تا راهنمایی بشی.",
        reply_markup=_contact_keyboard()
    )
    await state.set_state(Onboarding.waiting_for_license)


@router.message(Onboarding.waiting_for_license)
async def license_entered(message: Message, state: FSMContext, cfg, db_path: str):
    code = (message.text or "").strip().upper()
    lic = db.get_license(db_path, code)

    if not lic or lic.is_active != 1:
        await message.answer(
            "❌ کد اشتباهه\n\nدوباره تلاش کن یا از طریق دکمه زیر با مدیریت تماس بگیر:",
            reply_markup=_contact_keyboard()
        )
        return

    if lic.used_count >= lic.capacity:
        await message.answer(
            "⚠️ ظرفیت پر شده\n\nبرای رفع مشکل از طریق دکمه زیر با مدیریت تماس بگیر:",
            reply_markup=_contact_keyboard()
        )
        return

    role = "agency" if lic.license_type == "agency" else ("blogger" if lic.license_type == "blogger" else "direct_client")
    print(f"DEBUG: Upserting user {message.from_user.id} with role {role} and license {code} in handlers_start.py")
    db.upsert_user_on_license_join(
        db_path=db_path,
        user_id=message.from_user.id,
        role=role,
        full_name=message.from_user.full_name,
        license_code=code,
    )

    if lic.license_type == "agency" and not lic.agency_name:
        await state.set_state(Onboarding.waiting_for_agency_name)
        await message.answer("📍 لطفاً نام موسسه را وارد کنید:")
    elif lic.license_type == "blogger" and not lic.agency_name:
        await state.set_state(Onboarding.waiting_for_agency_name)
        await message.answer("🤳 لطفاً نام یا نام پیج خود را وارد کنید:")
    elif lic.license_type == "blogger":
        # Blogger has a name, but we need to ask for platform
        from .keyboards import kb_blogger_platforms
        await state.set_state(Onboarding.waiting_for_blogger_platform)
        await message.answer(
            "🤳 همکار گرامی، لطفاً پلتفرمی که در آن فعالیت می‌کنید را انتخاب کنید:",
            reply_markup=kb_blogger_platforms()
        )
    else:
        await state.set_state(Onboarding.waiting_for_contact)
        await message.answer(
            "📱 برای فعال‌سازی، شماره موبایل خود را ارسال کنید:",
            reply_markup=kb_request_contact(),
        )


@router.message(Onboarding.waiting_for_agency_name)
async def agency_name_entered(message: Message, state: FSMContext, db_path: str):
    agency_name = message.text.strip()
    user = db.get_user(db_path, message.from_user.id)
    if not user or not user.get("license_code"):
        await message.answer("خطایی رخ داد. مجدداً تلاش کنید.")
        return

    lic = db.get_license(db_path, user["license_code"])
    
    with db.connect(db_path) as conn:
        conn.execute("UPDATE licenses SET agency_name = ? WHERE code = ?", (agency_name, user["license_code"]))
    
    if lic and lic.license_type == "blogger":
        # Ask for platform for bloggers
        from .keyboards import kb_blogger_platforms
        await state.set_state(Onboarding.waiting_for_blogger_platform)
        await message.answer(
            "🤳 همکار گرامی، لطفاً پلتفرمی که در آن فعالیت می‌کنید را انتخاب کنید:",
            reply_markup=kb_blogger_platforms()
        )
    else:
        await state.set_state(Onboarding.waiting_for_agency_phone)
        await message.answer("📞 لطفاً شماره تماس موسسه را وارد کنید:")


@router.callback_query(Onboarding.waiting_for_blogger_platform)
async def blogger_platform_selected(callback: CallbackQuery, state: FSMContext, db_path: str):
    platform = callback.data.replace("platform_", "")
    platform_fa = {
        "instagram": "اینستاگرام",
        "website": "وب‌سایت",
        "telegram": "تلگرام"
    }.get(platform, platform)
    
    await state.update_data(blogger_platform=platform_fa)
    
    user = db.get_user(db_path, callback.from_user.id)
    with db.connect(db_path) as conn:
        conn.execute("UPDATE licenses SET blogger_platform = ? WHERE code = ?", (platform_fa, user["license_code"]))
    
    await state.set_state(Onboarding.waiting_for_blogger_platform_address)
    await callback.message.edit_text(f"🔗 لطفاً آدرس یا لینک {platform_fa} خود را وارد کنید:")


@router.message(Onboarding.waiting_for_blogger_platform_address)
async def blogger_platform_address_entered(message: Message, state: FSMContext, db_path: str):
    address = message.text.strip()
    user = db.get_user(db_path, message.from_user.id)
    
    with db.connect(db_path) as conn:
        conn.execute("UPDATE licenses SET blogger_platform_address = ? WHERE code = ?", (address, user["license_code"]))
    
    await state.set_state(Onboarding.waiting_for_contact)
    await message.answer(
        "📱 حالا شماره موبایل خود را ارسال کنید:",
        reply_markup=kb_request_contact(),
    )


@router.message(Onboarding.waiting_for_agency_phone)
async def agency_phone_entered(message: Message, state: FSMContext, db_path: str):
    agency_phone = message.text.strip()
    user = db.get_user(db_path, message.from_user.id)
    if user and user.get("license_code"):
        with db.connect(db_path) as conn:
            conn.execute("UPDATE licenses SET agency_phone = ? WHERE code = ?", (agency_phone, user["license_code"]))
    
    await state.set_state(Onboarding.waiting_for_agency_address)
    await message.answer("🏠 لطفاً آدرس دقیق موسسه را وارد کنید:")


@router.message(Onboarding.waiting_for_agency_address)
async def agency_address_entered(message: Message, state: FSMContext, db_path: str):
    agency_address = message.text.strip()
    user = db.get_user(db_path, message.from_user.id)
    if user and user.get("license_code"):
        with db.connect(db_path) as conn:
            conn.execute("UPDATE licenses SET agency_address = ? WHERE code = ?", (agency_address, user["license_code"]))
    
    await state.set_state(Onboarding.waiting_for_contact)
    await message.answer(
        "📱 حالا شماره موبایل خود را ارسال کنید:",
        reply_markup=kb_request_contact(),
    )


@router.message(Onboarding.waiting_for_contact)
async def contact_received(message: Message, state: FSMContext, cfg, db_path: str):
    if not message.contact or not message.contact.phone_number:
        await message.answer("لطفاً فقط از دکمه «ارسال شماره موبایل» استفاده کنید.")
        return

    if message.contact.user_id != message.from_user.id:
        await message.answer("شماره ارسالی باید متعلق به خودتان باشد. دوباره تلاش کنید.")
        return

    phone = message.contact.phone_number
    db.set_user_phone_verified(db_path, message.from_user.id, phone)

    user = db.get_user(db_path, message.from_user.id)
    lic = db.get_license(db_path, user["license_code"]) if user.get("license_code") else None
    
    await state.clear()
    
    if user["role"] == "agency":
        name = lic.agency_name if lic and lic.agency_name else (user.get("full_name") or "مدیر عزیز")
        capacity = lic.capacity if lic else "نامشخص"
        license_code = user["license_code"]
        
        welcome_text = (
            f"✅ لایسنس با موفقیت فعال شد 🎉\n\n"
            f"به خانواده مهاجرتی ایران آوسبیلدونگ خوش آمدید، {name} عزیز! 🌸\n\n"
            f"📋 اطلاعات لایسنس:\n"
            f"• کد لایسنس: {license_code}\n"
            f"• نفرات مجاز استفاده از ربات برای مجموعه شما: {capacity} نفر\n"
            f"• وضعیت: ✅ فعال\n\n"
            f"💡 راهنمای استفاده:\n"
            f"• شما می‌توانید پرونده‌های تخصیص داده شده را مدیریت کنید\n\n"
            f"برای دسترسی به منو، از دکمه‌های زیر استفاده کنید ✨"
        )
    elif user["role"] == "blogger":
        name = lic.agency_name if lic and lic.agency_name else "همکار"
        license_code = user["license_code"]
        
        welcome_text = (
            f"✅ لایسنس با موفقیت فعال شد 🎉\n\n"
            f"به خانواده مهاجرتی ایران آوسبیلدونگ خوش آمدید، همکار گرامی! 🌸\n\n"
            f"📋 اطلاعات لایسنس:\n"
            f"• کد لایسنس: {license_code}\n"
            f"• وضعیت: ✅ فعال\n\n"
            f"💡 راهنمای استفاده:\n"
            f"• شما می‌توانید پرونده‌های خود را مدیریت کنید\n\n"
            f"برای دسترسی به منو، از دکمه‌های زیر استفاده کنید ✨"
        )
    else:
        name = user.get("full_name") or "کاربر عزیز"
        license_code = user["license_code"]
        
        welcome_text = (
            f"✅ لایسنس با موفقیت فعال شد 🎉\n\n"
            f"به خانواده مهاجرتی ایران آوسبیلدونگ خوش آمدید، {name} عزیز! 🌸\n\n"
            f"📋 اطلاعات لایسنس:\n"
            f"• کد لایسنس: {license_code}\n"
            f"• وضعیت: ✅ فعال\n\n"
            f"💡 راهنمای استفاده:\n"
            f"• شما می‌توانید از خدمات ربات استفاده کنید\n\n"
            f"برای دسترسی به منو، از دکمه‌های زیر استفاده کنید ✨"
        )

    await message.answer(welcome_text, reply_markup=_menu_for_role(user["role"], db_path, message.from_user.id))
