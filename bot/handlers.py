from __future__ import annotations
import json
import random
import string
import re
from datetime import datetime

from aiogram import Router, F, Bot
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

from . import db
from .gdrive_utils import GDriveService
import os
import io
import asyncio
from .keyboards import (
    kb_admin_main, kb_agency_main, kb_direct_client_main, kb_back_main,
    kb_licenses_menu, kb_cases_menu, kb_cases_owner_type, kb_tickets_menu,
    kb_interviews_menu, kb_send_message_menu, kb_admins_menu,
    kb_field_selection,
    kb_document_upload, kb_document_submit, kb_case_detail, kb_status_change,
    kb_license_detail, kb_yes_no, kb_request_contact, kb_open_tickets_list,
    kb_ticket_actions, kb_user_ticket_actions, kb_agency_selection, kb_client_license_selection,
    kb_case_selection, kb_visa_types, kb_add_more_fields
)
from .states import (
    Onboarding, LicenseManagement, CaseManagement, DocumentUpload,
    DocumentReview, TicketManagement, InterviewManagement, MessageManagement,
    AdminManagement, SMSTest, InstallmentReminder
)
from .sms_service import sms_service

router = Router()

BRAND_NAME = "ایران آوسبیلدونگ"
CONTACT_LINK = "https://wa.me/message/2N2G7P6T3V7TB1"


def _contact_keyboard():
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 تماس با پشتیبانی واتساپ", url=CONTACT_LINK)]
    ])
AGENCY_DOCS = ["رزومه", "عکس شخص", "مدارک تحصیلی", "مدارک شغلی", "مدرک زبان", "عکس امضا", "عکس پاسپورت"]
CLIENT_DOCS = ["رزومه", "عکس شخص", "مدارک تحصیلی", "مدارک شغلی", "مدرک زبان", "عکس امضا", "عکس پاسپورت"]

DOC_TYPE_MAPPING = {
    "رزومه": "Lebenslauf",
    "عکس شخص": "PersonalPhoto",
    "مدارک تحصیلی": "SchulZeugniss",
    "مدرک تحصیلی": "SchulZeugniss",
    "مدارک شغلی": "ArbeitZeugniss",
    "مدرک شغلی": "ArbeitZeugniss",
    "مدرک زبان": "SprachZertifikat",
    "عکس امضا": "Unterschrift",
    "عکس پاسپورت": "ReisePass"
}


def get_status_display(status: str, reason: str = None) -> str:
    """نمایش وضعیت با رنگ مناسب"""
    if status == "green":
        return "🟢 فعال"
    elif status == "yellow":
        if reason:
            return f"🟡 غیرفعال ({reason})"
        return "🟡 غیرفعال"
    elif status == "red":
        return "🔴 نیاز به توجه"
    else:
        return "⚪ پایان یافته"


def format_amount(amount: float) -> str:
    """فرمت کردن مبلغ با €"""
    return f"{amount:,.0f}€"


def gen_license_code(length: int = 10) -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=length))


def menu_for_role(role: str, db_path: str = None, user_id: int = None):
    if role in ("super_admin", "admin"):
        perms = None
        if role == "admin" and db_path and user_id:
            perms = db.get_admin_permissions(db_path, user_id)
        return kb_admin_main(role=role, perms=perms)
    if role == "agency":
        return kb_agency_main()
    if role == "blogger":
        return kb_agency_main()
    return kb_direct_client_main()


def has_permission(db_path: str, user_id: int, permission: str) -> bool:
    user = db.get_user(db_path, user_id)
    if not user:
        return False
    if user["role"] == "super_admin":
        return True
    if user["role"] == "admin":
        perms = db.get_admin_permissions(db_path, user_id)
        if not perms:
            return False
        return bool(perms.get(permission, 0))
    return False


def get_smart_kb(kb_func, user_id: int, db_path: str):
    user = db.get_user(db_path, user_id)
    if not user:
        return kb_func()
    role = user["role"]
    perms = db.get_admin_permissions(db_path, user_id) if role == "admin" else None
    return kb_func(role=role, perms=perms)

@router.message(F.text.in_(["بازگشت به مرحله قبل", "🔙 بازگشت به مرحله قبل"]))
async def back_step(message: Message, state: FSMContext, cfg, db_path: str):
    await state.clear()
    user = db.get_user(db_path, message.from_user.id)
    if user:
        await message.answer("بازگشت...", reply_markup=menu_for_role(user["role"], db_path, message.from_user.id))


@router.message(F.text.in_(["منوی اصلی", "🏠 منوی اصلی"]))
async def back_to_main(message: Message, state: FSMContext, cfg, db_path: str):
    await state.clear()
    user = db.get_user(db_path, message.from_user.id)
    if user:
        await message.answer("🏠 یکی از گزینه‌های زیر رو انتخاب کن:", reply_markup=menu_for_role(user["role"], db_path, message.from_user.id))
    else:
        await message.answer("اول /start رو بزن!")


@router.message(CommandStart())
async def start_cmd(message: Message, state: FSMContext, cfg, db_path: str):
    user_id = message.from_user.id
    if user_id == cfg.super_admin_id:
        db.upsert_user_on_license_join(db_path, user_id, "super_admin", message.from_user.full_name, "")
        await message.answer(f"✨ {BRAND_NAME}\n\n🛠️ پنل مدیریت\n\nبه سیستم خوش اومدی! 👋", reply_markup=kb_admin_main())
        await state.clear()
        return
    user = db.get_user(db_path, user_id)

    # ادمین‌هایی که از پنل اضافه شدند (phone_verified ممکنه 0 باشه)
    if user and user["role"] in ("admin", "super_admin"):
        name = user.get("full_name", "ادمین عزیز")
        await message.answer(
            f"✨ {BRAND_NAME}\n\n🛠️ پنل مدیریت\n\nسلام {name}! خوش اومدی 👋",
            reply_markup=menu_for_role(user["role"], db_path, user["user_id"])
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
            await message.answer(f"✨ {BRAND_NAME}\n\nسلام {name}! 🏢\n\nخوش اومدی! امیدوارم روزت عالی باشه 👋", reply_markup=menu_for_role(user["role"], db_path, user_id))
        elif user["role"] == "blogger":
            await message.answer(f"✨ {BRAND_NAME}\n\nسلام همکار گرامی! 🤳\n\nخوش اومدی! امیدوارم روزت عالی باشه 👋", reply_markup=menu_for_role(user["role"], db_path, user_id))
        else:
            await message.answer(f"✨ {BRAND_NAME}\n\nسلام {name}! 🌸\n\nخوش اومدی! امیدوارم همه چیز عالی پیش بره 👋", reply_markup=menu_for_role(user["role"], db_path, user_id))
        await state.clear()
        return
    await message.answer(
        f"✨ {BRAND_NAME}\n\nکد لایسنس رو وارد کن:\n\n💡 اگه تو لایسنست مشکل داری یا لایسنس دریافت نکردی، از دکمه پایین به مدیریت در واتساپ پیام بده تا راهنمایی بشی.",
        reply_markup=_contact_keyboard()
    )
    await state.set_state(Onboarding.waiting_for_license)


@router.message(Onboarding.waiting_for_license)
async def license_entered(message: Message, state: FSMContext, cfg, db_path: str):
    code = message.text.strip().upper()
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
    print(f"DEBUG: Upserting user {message.from_user.id} with role {role} and license {code}")
    db.upsert_user_on_license_join(db_path, message.from_user.id, role, message.from_user.full_name, code)
    if lic.license_type == "agency":
        if not lic.agency_name:
            await state.set_state(Onboarding.waiting_for_agency_name)
            await message.answer("📍 لطفاً نام موسسه را وارد کنید:")
            return
    elif lic.license_type == "blogger":
        if not lic.agency_name:
            await state.set_state(Onboarding.waiting_for_agency_name)
            await message.answer("🤳 لطفاً نام یا نام پیج خود را وارد کنید:")
            return
    
    await state.set_state(Onboarding.waiting_for_contact)
    await message.answer(
        "📱 برای فعال‌سازی، شماره موبایل خود را ارسال کنید:",
        reply_markup=kb_request_contact()
    )


@router.message(Onboarding.waiting_for_agency_name)
async def agency_name_entered(message: Message, state: FSMContext, db_path: str):
    agency_name = message.text.strip()
    user_id = message.from_user.id
    user = db.get_user(db_path, user_id)
    if not user or not user.get("license_code"):
        await message.answer("خطایی رخ داد. مجدداً تلاش کنید.")
        return

    lic = db.get_license(db_path, user["license_code"])
    
    from . import db as db_module
    with db_module.connect(db_path) as conn:
        conn.execute("UPDATE licenses SET agency_name = ? WHERE code = ?", (agency_name, user["license_code"]))
    
    if lic and lic.license_type == "blogger":
        # Skip address/phone for bloggers
        await state.set_state(Onboarding.waiting_for_contact)
        await message.answer(
            "📱 حالا شماره موبایل خود را ارسال کنید:",
            reply_markup=kb_request_contact()
        )
    else:
        await state.set_state(Onboarding.waiting_for_agency_phone)
        await message.answer("📞 لطفاً شماره تماس موسسه را وارد کنید:")


@router.message(Onboarding.waiting_for_agency_phone)
async def agency_phone_entered(message: Message, state: FSMContext, db_path: str):
    agency_phone = message.text.strip()
    user_id = message.from_user.id
    user = db.get_user(db_path, user_id)
    if user and user.get("license_code"):
        from . import db as db_module
        with db_module.connect(db_path) as conn:
            conn.execute("UPDATE licenses SET agency_phone = ? WHERE code = ?", (agency_phone, user["license_code"]))
    
    await state.set_state(Onboarding.waiting_for_agency_address)
    await message.answer("🏠 لطفاً آدرس دقیق موسسه را وارد کنید:")


@router.message(Onboarding.waiting_for_agency_address)
async def agency_address_entered(message: Message, state: FSMContext, db_path: str):
    agency_address = message.text.strip()
    user_id = message.from_user.id
    user = db.get_user(db_path, user_id)
    if user and user.get("license_code"):
        from . import db as db_module
        with db_module.connect(db_path) as conn:
            conn.execute("UPDATE licenses SET agency_address = ? WHERE code = ?", (agency_address, user["license_code"]))
    
    await state.set_state(Onboarding.waiting_for_contact)
    await message.answer(
        "📱 حالا شماره موبایل خود را ارسال کنید:",
        reply_markup=kb_request_contact()
    )


@router.message(Onboarding.waiting_for_contact, F.contact)
async def contact_received(message: Message, state: FSMContext, db_path: str):
    if not message.contact or message.contact.user_id != message.from_user.id:
        await message.answer("لطفاً شماره خودتان را ارسال کنید.")
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

    await message.answer(welcome_text, reply_markup=menu_for_role(user["role"], db_path, message.from_user.id))


@router.message(F.text == "🔑 لایسنس‌ها")
async def licenses_menu(message: Message, state: FSMContext, cfg, db_path: str):
    if not has_permission(db_path, message.from_user.id, "can_manage_licenses"):
        await message.answer("❌ شما به این بخش دسترسی ندارید.")
        return
    await message.answer("🔑 مدیریت لایسنس‌ها:", reply_markup=get_smart_kb(kb_licenses_menu, message.from_user.id, db_path))


@router.message(F.text == "📋 اطلاعات کاربران")
async def user_info_selector(message: Message, db_path: str):
    user = db.get_user(db_path, message.from_user.id)
    if user["role"] != "super_admin":
        await message.answer("❌ این بخش فقط برای سوپر ادمین در دسترس است.")
        return
    
    # Create inline keyboard for user type selection
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏢 موسسات", callback_data="info_type_agency")],
        [InlineKeyboardButton(text="🤳 بلاگرها", callback_data="info_type_blogger")],
        [InlineKeyboardButton(text="👤 کلاینت‌ها", callback_data="info_type_client")],
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="back_to_licenses_menu")]
    ])
    
    await message.answer("📋 انتخاب نوع کاربر برای مشاهده اطلاعات:", reply_markup=keyboard)


def kb_user_info_selection(agencies: list, action_prefix: str) -> InlineKeyboardMarkup:
    """Specific keyboard for user info selection to avoid callback conflicts"""
    buttons = []
    for ag in agencies:
        callback = f"{action_prefix}_{ag['code']}"
        # Use appropriate emoji based on action prefix
        emoji = "🏢" if "agency" in action_prefix else ("🤳" if "blogger" in action_prefix else "👤")
        buttons.append([InlineKeyboardButton(text=f"{emoji} {ag['agency_name']} ({ag['code']})", callback_data=callback)])
    
    # Always use back_to_user_type_selection for consistency
    buttons.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="back_to_user_type_selection")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.callback_query(F.data.startswith("info_type_"))
async def handle_user_type_selection(callback: CallbackQuery, db_path: str):
    user_type = callback.data.replace("info_type_", "")
    licenses = db.get_all_licenses(db_path)
    
    if user_type == "agency":
        filtered_licenses = [lic for lic in licenses if lic["license_type"] == "agency"]
        if not filtered_licenses:
            await callback.answer("❌ هیچ موسسه‌ای ثبت نشده است.")
            return
        await callback.message.edit_text("🏢 کدام موسسه را می‌خواهید مشاهده کنید؟", 
                                     reply_markup=kb_user_info_selection(filtered_licenses, "view_agency_info"))
    elif user_type == "blogger":
        filtered_licenses = [lic for lic in licenses if lic["license_type"] == "blogger"]
        if not filtered_licenses:
            await callback.answer("❌ هیچ بلاگری ثبت نشده است.")
            return
        await callback.message.edit_text("🤳 کدام بلاگر را می‌خواهید مشاهده کنید؟", 
                                     reply_markup=kb_user_info_selection(filtered_licenses, "view_blogger_info"))
    elif user_type == "client":
        filtered_licenses = [lic for lic in licenses if lic["license_type"] == "direct_client"]
        if not filtered_licenses:
            await callback.answer("❌ هیچ کلاینتی ثبت نشده است.")
            return
        await callback.message.edit_text("👤 کدام کلاینت را می‌خواهید مشاهده کنید؟", 
                                     reply_markup=kb_user_info_selection(filtered_licenses, "view_client_info"))


@router.callback_query(F.data.startswith("view_agency_info_"))
async def show_agency_info(callback: CallbackQuery, db_path: str):
    code = callback.data.replace("view_agency_info_", "")
    lic = db.get_license(db_path, code)
    
    if not lic:
        await callback.answer("❌ لایسنس یافت نشد.")
        return
    
    members = db.get_license_members(db_path, code)
    members_text = ""
    personal_phones = ""
    
    for m in members:
        role_fa = "مدیر" if m['role'] == 'agency' else "کاربر"
        verified = "✅" if m['is_phone_verified'] else "❌"
        members_text += f"👤 {m['full_name'] or 'نامشخص'} ({role_fa}) | {verified}\n"
        
        # Collect personal phone numbers (shared on Telegram)
        if m.get('phone'):
            personal_phones += f"📱 {m['phone']}\n"
    
    info_text = (
        f"🏢 اطلاعات موسسه: {lic.agency_name or 'نامشخص'}\n"
        f"━━━━━━━━━━━━━━━\n"
        f"🔑 کد لایسنس: {lic.code}\n\n"
        f"📞 شماره دفتر موسسه:\n{lic.agency_phone or 'ثبت نشده'}\n\n"
        f"📱 شماره تماس شخصی (همان شماره‌ای که در تلگرام ثبت شده):\n{personal_phones or 'ثبت نشده'}\n\n"
        f"🏠 آدرس موسسه:\n{lic.agency_address or 'ثبت نشده'}\n\n"
        f"👥 اعضا ({lic.used_count}/{lic.capacity}):\n"
        f"{members_text or '⚠️ هیچ عضوی ندارد'}"
    )
    
    await callback.message.edit_text(info_text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 بازگشت به لیست", callback_data="back_to_user_type_selection")]
    ]))


@router.callback_query(F.data.startswith("view_blogger_info_"))
async def show_blogger_info(callback: CallbackQuery, db_path: str):
    code = callback.data.replace("view_blogger_info_", "")
    lic = db.get_license(db_path, code)
    
    if not lic:
        await callback.answer("❌ لایسنس یافت نشد.")
        return
    
    members = db.get_license_members(db_path, code)
    members_text = ""
    for m in members:
        verified = "✅" if m['is_phone_verified'] else "❌"
        members_text += f"👤 {m['full_name'] or 'نامشخص'} | {verified}\n"
    
    info_text = (
        f"🤳 اطلاعات بلاگر: {lic.agency_name or 'نامشخص'}\n"
        f"━━━━━━━━━━━━━━━\n"
        f"🔑 کد لایسنس: {lic.code}\n"
        f"📱 شماره تماس: {lic.agency_phone or 'ثبت نشده'}\n"
        f"🌐 پلتفرم: {getattr(lic, 'blogger_platform', 'ثبت نشده')}\n"
        f"🔗 آیدی/لینک: {lic.agency_name or 'ثبت نشده'}\n\n"
        f"👥 اعضا ({lic.used_count}/{lic.capacity}):\n"
        f"{members_text or '⚠️ هیچ عضوی ندارد'}"
    )
    
    await callback.message.edit_text(info_text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 بازگشت به لیست", callback_data="back_to_user_type_selection")]
    ]))


@router.callback_query(F.data.startswith("view_client_info_"))
async def show_client_info(callback: CallbackQuery, db_path: str):
    code = callback.data.replace("view_client_info_", "")
    lic = db.get_license(db_path, code)
    
    if not lic:
        await callback.answer("❌ لایسنس یافت نشد.")
        return
    
    members = db.get_license_members(db_path, code)
    phone_text = ""
    
    for m in members:
        # Phone they shared when getting license (from users table)
        if m.get('phone'):
            phone_text += f"📱 {m['phone']}\n"
    
    info_text = (
        f"👤 اطلاعات کلاینت: {lic.agency_name or 'نامشخص'}\n"
        f"━━━━━━━━━━━━━━━\n"
        f"🔑 کد لایسنس: {lic.code}\n\n"
        f"📱 شماره تماس:\n"
        f"{phone_text or '⚠️ شماره‌ای ثبت نشده'}"
    )
    
    await callback.message.edit_text(info_text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 بازگشت به لیست", callback_data="back_to_user_type_selection")]
    ]))


@router.callback_query(F.data == "back_to_user_type_selection")
async def back_to_user_type_selection(callback: CallbackQuery, db_path: str):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏢 موسسات", callback_data="info_type_agency")],
        [InlineKeyboardButton(text="🤳 بلاگرها", callback_data="info_type_blogger")],
        [InlineKeyboardButton(text="👤 کلاینت‌ها", callback_data="info_type_client")],
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="back_to_licenses_menu")]
    ])
    
    await callback.message.edit_text("📋 انتخاب نوع کاربر برای مشاهده اطلاعات:", reply_markup=keyboard)


@router.callback_query(F.data == "back_to_licenses_menu")
async def back_to_licenses_menu(callback: CallbackQuery, db_path: str):
    from .keyboards import kb_licenses_menu
    user = db.get_user(db_path, callback.from_user.id)
    if user:
        await callback.message.edit_text("🔑 مدیریت لایسنس‌ها:", reply_markup=get_smart_kb(kb_licenses_menu, callback.from_user.id, db_path))


@router.message(F.text == "📁 پرونده‌ها")
async def cases_menu(message: Message, state: FSMContext, cfg, db_path: str):
    if not has_permission(db_path, message.from_user.id, "can_manage_cases"):
        await message.answer("❌ شما به این بخش دسترسی ندارید.")
        return
    await message.answer("📁 مدیریت پرونده‌ها:", reply_markup=get_smart_kb(kb_cases_menu, message.from_user.id, db_path))


@router.message(F.text == "🎫 تیکت‌ها")
async def tickets_menu(message: Message, state: FSMContext, cfg, db_path: str):
    user = db.get_user(db_path, message.from_user.id)
    if user and user["role"] in ("super_admin", "admin"):
        if not has_permission(db_path, message.from_user.id, "can_manage_tickets"):
            await message.answer("❌ شما به این بخش دسترسی ندارید.")
            return
        await message.answer("🎫 مدیریت تیکت‌ها:", reply_markup=get_smart_kb(kb_tickets_menu, message.from_user.id, db_path))
    elif user and user["role"] in ("agency", "direct_client"):
        await state.set_state(TicketManagement.creating_ticket)
        await message.answer("🎫 ثبت تیکت جدید\n\nلطفا متن تیکت خود را وارد کنید:")


@router.message(F.text == "📅 مصاحبه‌های جدید")
async def interviews_menu(message: Message, state: FSMContext, cfg, db_path: str):
    if not has_permission(db_path, message.from_user.id, "can_manage_interviews"):
        await message.answer("❌ شما به این بخش دسترسی ندارید.")
        return
    await message.answer("📅 مدیریت مصاحبه‌ها:", reply_markup=get_smart_kb(kb_interviews_menu, message.from_user.id, db_path))


@router.message(F.text == "📆 مصاحبه‌های ۱۰ روز آینده")
async def upcoming_interviews_10_days(message: Message, db_path: str):
    if not has_permission(db_path, message.from_user.id, "can_manage_interviews"):
        await message.answer("❌ شما به این بخش دسترسی ندارید.")
        return

    from datetime import datetime, timedelta

    now = datetime.now()
    end = now + timedelta(days=10)
    start_iso = now.isoformat(timespec="seconds")
    end_iso = end.isoformat(timespec="seconds")

    interviews = db.get_interviews_between(db_path, start_iso, end_iso)

    valid: list[dict] = []
    for iv in interviews:
        if iv.get("status") in ("cancelled", "completed", "no_show"):
            continue
        if not iv.get("scheduled_at_iso"):
            continue
        try:
            datetime.fromisoformat(iv["scheduled_at_iso"])
        except Exception:
            continue
        valid.append(iv)

    if not valid:
        await message.answer("📆 مصاحبه‌های ۱۰ روز آینده\n\nℹ️ مصاحبه‌ای در ۱۰ روز آینده ثبت نشده است.", reply_markup=get_smart_kb(kb_interviews_menu, message.from_user.id, db_path))
        return

    def _fmt_dt(iso_str: str) -> tuple[str, str, str]:
        dt = datetime.fromisoformat(iso_str)
        date_str = dt.strftime("%Y/%m/%d")
        time_str = dt.strftime("%H:%M")
        
        diff = dt.date() - datetime.now().date()
        days_diff = diff.days
        if days_diff == 0:
            rem_str = "(امروز)"
        elif days_diff == 1:
            rem_str = "(فردا)"
        elif days_diff > 1:
            rem_str = f"({days_diff} روز دیگه)"
        else:
            rem_str = ""
            
        return date_str, time_str, rem_str

    lines: list[str] = []
    lines.append("📅 مصاحبه‌های ۱۰ روز آینده")
    lines.append(f"از `{now.strftime('%Y/%m/%d %H:%M')}` تا `{end.strftime('%Y/%m/%d %H:%M')}`")
    lines.append("⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯")

    current_date = None
    for iv in valid:
        date_str, time_str, rem_str = _fmt_dt(iv["scheduled_at_iso"])
        if date_str != current_date:
            current_date = date_str
            lines.append("")
            lines.append(f"📅 {date_str} {rem_str}")

        case = db.get_case(db_path, iv.get("case_id")) if iv.get("case_id") else None
        owner_type = (case or {}).get("owner_type")
        owner_code = (case or {}).get("owner_license_code")
        lic = db.get_license(db_path, owner_code) if owner_code else None

        owner_label = ""
        if owner_type == "agency":
            owner_label = f"🏢 موسسه: {getattr(lic, 'agency_name', None) or owner_code or 'نامشخص'}"
        elif owner_type == "blogger":
            owner_label = f"🤳 بلاگر: {getattr(lic, 'agency_name', None) or owner_code or 'نامشخص'}"
        elif owner_type == "direct_client":
            owner_label = f"👤 کلاینت: {getattr(lic, 'agency_name', None) or owner_code or 'نامشخص'}"
        else:
            owner_label = f"👤 مالک پرونده: {owner_code or 'نامشخص'}"

        case_id = (case or {}).get("case_id") or iv.get("case_id") or "نامشخص"
        client_name = (case or {}).get("client_name") or "نامشخص"

        company_name = iv.get("company_name") or iv.get("employer_name") or "نامشخص"
        city = iv.get("city") or "-"
        platform = iv.get("platform") or "-"
        meeting_link = iv.get("meeting_link") or "-"
        username = iv.get("username") or "-"
        password = iv.get("password") or "-"

        lines.append(f"- {time_str} | پرونده `{case_id}`")
        lines.append(f"  - متقاضی: {client_name}")
        lines.append(f"  - {owner_label}")
        lines.append(f"  - شرکت/کارفرما: {company_name}")
        lines.append(f"  - شهر: {city}")
        lines.append(f"  - پلتفرم: {platform}")
        lines.append(f"  - لینک جلسه: {meeting_link}")
        lines.append(f"  - یوزرنیم: {username}")
        lines.append(f"  - پسورد: {password}")

    text = "\n".join(lines).strip()

    # Telegram message length limit safety
    max_len = 3500
    if len(text) <= max_len:
        await message.answer(text, parse_mode="Markdown", disable_web_page_preview=True, reply_markup=get_smart_kb(kb_interviews_menu, message.from_user.id, db_path))
        return

    # Split by lines into multiple messages
    chunks: list[str] = []
    buf: list[str] = []
    curr = 0
    for ln in text.split("\n"):
        add = len(ln) + 1
        if curr + add > max_len and buf:
            chunks.append("\n".join(buf))
            buf = [ln]
            curr = len(ln) + 1
        else:
            buf.append(ln)
            curr += add
    if buf:
        chunks.append("\n".join(buf))

    for i, chunk in enumerate(chunks):
        await message.answer(chunk, parse_mode="Markdown", disable_web_page_preview=True)
    await message.answer("✅ پایان گزارش.", reply_markup=get_smart_kb(kb_interviews_menu, message.from_user.id, db_path))


@router.message(F.text == "💬 ارسال پیام")
async def message_menu(message: Message, state: FSMContext, cfg, db_path: str):
    if not has_permission(db_path, message.from_user.id, "can_send_messages"):
        await message.answer("❌ شما به این بخش دسترسی ندارید.")
        return
    await message.answer("💬 ارسال پیام:", reply_markup=get_smart_kb(kb_send_message_menu, message.from_user.id, db_path))


@router.message(F.text == "👥 ادمین‌ها")
async def admins_menu(message: Message, state: FSMContext, cfg, db_path: str):
    if not has_permission(db_path, message.from_user.id, "can_manage_admins"):
        await message.answer("❌ شما به این بخش دسترسی ندارید.")
        return
    await message.answer("👥 مدیریت ادمین‌ها:", reply_markup=get_smart_kb(kb_admins_menu, message.from_user.id, db_path))


@router.message(F.text == "📊 آمار")
async def show_dashboard(message: Message, db_path: str):
    user = db.get_user(db_path, message.from_user.id)
    if not user or user["role"] != "super_admin":
        await message.answer("❌ دسترسی غیرمجاز. این بخش فقط برای سوپرادمین است.")
        return

    all_cases = db.get_all_cases(db_path)
    all_tickets = db.get_all_tickets(db_path)
    all_agencies = db.get_all_agencies(db_path)
    registered_agencies = db.get_users_by_role(db_path, "agency")
    all_direct_clients = db.get_all_direct_clients(db_path)
    registered_clients = db.get_users_by_role(db_path, "direct_client")
    all_blogger_licenses = [lic for lic in db.get_all_licenses(db_path) if lic["license_type"] == "blogger"]
    active_blogger_licenses = [lic for lic in all_blogger_licenses if lic["is_active"]]

    total_amount = sum(c.get("total_amount", 0) for c in all_cases)
    active_cases = len([c for c in all_cases if c.get("status") == "green"])
    inactive_cases = len([c for c in all_cases if c.get("status") == "yellow"])
    red_cases = len([c for c in all_cases if c.get("status") == "red"])
    ended_cases = len([c for c in all_cases if c.get("status") == "archived"])
    open_tickets = len([t for t in all_tickets if t.get("status") == "open"])
    closed_tickets = len(all_tickets) - open_tickets

    # محاسبه نرخ پاسخگویی و موفقیت (فرضی برای ارتقا)
    ticket_success_rate = (closed_tickets / len(all_tickets) * 100) if all_tickets else 0
    
    text = f"""
📊 گزارش جامع مدیریت سیستم
{'━'*15}

👥 وضعیت کاربران
├ 🏛 موسسات: `{len(all_agencies)}` (فعال: {len(registered_agencies)})
├ 👤 کلاینت‌های مستقیم: `{len(all_direct_clients)}` (فعال: {len(registered_clients)})
└ 🤳 بلاگرها: `{len(all_blogger_licenses)}` (فعال: {len(active_blogger_licenses)})

📁 مدیریت پرونده‌ها
├ 🟢 فعال و در جریان: `{active_cases}`
├ 🟡 موقت متوقف شده: `{inactive_cases}`
├ 🔴 نیازمند بررسی آنی: `{red_cases}`
├ 🏁 پایان یافته: `{ended_cases}`
└ 📊 مجموع کل پرونده‌ها: `{len(all_cases)}`

🎫 پشتیبانی و تیکت‌ها
├ 📥 تیکت‌های باز: `{open_tickets}`
├ 🏁 تیکت‌های بسته‌شده: `{closed_tickets}`
└ 📈 نرخ پاسخگویی: `{ticket_success_rate:.1f}%`

💰 خلاصه مالی
└ 💎 ارزش کل قراردادها:
   {format_amount(total_amount)}

{'━'*15}
🕒 به‌روزرسانی: `{datetime.now().strftime('%H:%M - %Y/%m/%d')}`
"""

    await message.answer(text, reply_markup=menu_for_role("super_admin", db_path, message.from_user.id), parse_mode="Markdown")


@router.message(F.text == "➕ ساخت لایسنس بلاگر")
async def create_license_blogger(message: Message, state: FSMContext, db_path: str):
    await state.set_state(LicenseManagement.entering_blogger_name)
    await message.answer("نام یا نام پیج بلاگر را وارد کنید:")


@router.message(LicenseManagement.entering_blogger_name)
async def enter_blogger_name(message: Message, state: FSMContext, db_path: str):
    await state.update_data(agency_name=message.text.strip(), license_type="blogger")
    await state.set_state(LicenseManagement.entering_capacity)
    await message.answer("ظرفیت را وارد کنید (عدد):")


@router.message(F.text == "👁 لایسنس‌های بلاگرها")
async def view_blogger_licenses(message: Message, db_path: str):
    licenses = db.get_all_licenses(db_path)
    filtered_licenses = [lic for lic in licenses if lic["license_type"] == "blogger"]
    
    if not filtered_licenses:
        await message.answer("❌ هیچ لایسنس بلاگری در سیستم ثبت نشده است.")
        return
    
    text = "🤳 لیست لایسنس‌های بلاگرها"
    text += "━" * 15 + "\n\n"
    
    for lic in filtered_licenses:
        status_emoji = "✅" if lic["is_active"] else "❌"
        name = lic['agency_name'] or 'بدون نام'
        code = str(lic['code']).replace("-", "\\-").replace(".", "\\.")
        name_esc = str(name).replace("-", "\\-").replace(".", "\\.")
        
        text += (
            f"{name_esc}\n"
            f"🆔 کد: `{code}`\n"
            f"📌 پلتفرم: {lic.get('blogger_platform', 'ثبت نشده')}\n"
            f"📌 وضعیت: {status_emoji}\n"
            f"{'─' * 15}\n\n"
        )
    
    try:
        await message.answer(text, reply_markup=get_smart_kb(kb_licenses_menu, message.from_user.id, db_path), parse_mode="MarkdownV2")
    except Exception as e:
        fallback_text = text.replace("\\", "").replace("`", "").replace("*", "")
        await message.answer(fallback_text, reply_markup=get_smart_kb(kb_licenses_menu, message.from_user.id, db_path))


@router.message(F.text == "🤳 ارسال به بلاگر")
async def send_message_to_blogger(message: Message, state: FSMContext, db_path: str):
    licenses = db.get_all_licenses(db_path)
    bloggers = [lic for lic in licenses if lic["license_type"] == "blogger"]
    
    if not bloggers:
        await message.answer("❌ هیچ بلاگری ثبت نشده است.")
        return
    
    await message.answer("🤳 انتخاب بلاگر برای ارسال پیام:", reply_markup=kb_agency_selection(bloggers, "msg_blogger"))


@router.callback_query(F.data.startswith("msg_blogger_"))
async def blogger_selected_for_msg(callback: CallbackQuery, state: FSMContext):
    code = callback.data.replace("msg_blogger_", "")
    await state.update_data(target_license_code=code, recipient_type="blogger")
    await state.set_state(MessageManagement.entering_message_text)
    await callback.message.edit_text("💬 متن پیام خود را برای بلاگر وارد کنید:")


@router.message(F.text == "⭐ ویژه کردن موسسه")
async def toggle_special_institution_start(message: Message, state: FSMContext, db_path: str):
    await message.answer("⚠️ این بخش حذف شده و با بخش بلاگرها جایگزین شده است.")


@router.message(F.text == "➕ ساخت لایسنس موسسه")
async def create_license_agency(message: Message, state: FSMContext, db_path: str):
    await state.set_state(LicenseManagement.entering_agency_name)
    await message.answer("نام موسسه را وارد کنید:")


@router.message(LicenseManagement.entering_agency_name)
async def enter_agency_name(message: Message, state: FSMContext, db_path: str):
    await state.update_data(agency_name=message.text.strip(), license_type="agency")
    await state.set_state(LicenseManagement.entering_capacity)
    await message.answer("ظرفیت را وارد کنید (عدد):")


@router.message(LicenseManagement.entering_capacity)
async def enter_capacity(message: Message, state: FSMContext, db_path: str):
    try:
        capacity = int(message.text.strip())
        data = await state.get_data()
        license_type = data.get("license_type", "agency")
        code = gen_license_code()
        db.create_license(db_path, code, license_type, capacity, data.get("agency_name"))
        type_fa = "موسسه" if license_type == "agency" else "بلاگر"
        await message.answer(f"✅ لایسنس {type_fa} ساخته شد:\n\nکد: `{code}`\nظرفیت: {capacity}\nنام: {data.get('agency_name')}", reply_markup=get_smart_kb(kb_licenses_menu, message.from_user.id, db_path), parse_mode="Markdown")
        await state.clear()
    except ValueError:
        await message.answer("لطفاً عدد وارد کنید:")


@router.message(F.text == "➕ ساخت لایسنس کلاینت")
async def create_license_client(message: Message, state: FSMContext, db_path: str):
    await state.set_state(LicenseManagement.entering_client_name)
    await message.answer("نام کلاینت را وارد کنید:")


@router.message(LicenseManagement.entering_client_name)
async def enter_client_name_for_license(message: Message, state: FSMContext, db_path: str):
    code = gen_license_code()
    db.create_license(db_path, code, "direct_client", 1, message.text.strip())
    await message.answer(f"✅ لایسنس کلاینت ساخته شد:\n\nکد: `{code}`\nظرفیت: 1\nنام: {message.text.strip()}", reply_markup=get_smart_kb(kb_licenses_menu, message.from_user.id, db_path), parse_mode="Markdown")
    await state.clear()


@router.message(F.text.in_(["👁 لایسنس‌های موسسات", "👁 لایسنس‌های کلاینت‌ها"]))
async def view_licenses(message: Message, db_path: str):
    target_type = "agency" if "موسسات" in message.text else "direct_client"
    
    licenses = db.get_all_licenses(db_path)
    filtered_licenses = [lic for lic in licenses if lic["license_type"] == target_type]
    
    if not filtered_licenses:
        type_name = "موسسه" if target_type == "agency" else "کلاینت"
        await message.answer(f"❌ هیچ لایسنس {type_name}‌ای در سیستم ثبت نشده است.")
        return
    
    title = "🏢 لیست لایسنس‌های موسسات" if target_type == "agency" else "👤 لیست لایسنس‌های کلاینت‌ها"
    text = f"{title}\n"
    text += "━" * 15 + "\n\n"
    
    for lic in filtered_licenses:
        status_emoji = "✅" if lic["is_active"] else "❌"
        
        name = lic['agency_name'] or 'بدون نام'
        code = str(lic['code']).replace("-", "\\-").replace(".", "\\.")
        name_esc = str(name).replace("-", "\\-").replace(".", "\\.")
        used = str(lic['used_count'])
        total = str(lic['capacity'])
        
        text += (
            f"{name_esc}\n"
            f"🆔 کد: `{code}`\n"
            f"📊 ظرفیت: `{used}/{total}`\n"
            f"📌 وضعیت: {status_emoji}\n"
            f"{'─' * 15}\n\n"
        )
    
    try:
        await message.answer(text, reply_markup=get_smart_kb(kb_licenses_menu, message.from_user.id, db_path), parse_mode="MarkdownV2")
    except Exception as e:
        import logging
        logging.error(f"Error sending MarkdownV2 message: {e}")
        fallback_text = text.replace("\\", "").replace("`", "").replace("*", "")
        await message.answer(fallback_text, reply_markup=get_smart_kb(kb_licenses_menu, message.from_user.id, db_path))


@router.message(F.text == "👁 مشاهده پرونده‌ها")
async def view_cases(message: Message, state: FSMContext, db_path: str):
    user = db.get_user(db_path, message.from_user.id)
    if not user: return

    if user["role"] in ("super_admin", "admin"):
        from .keyboards import kb_case_owner_type_inline
        await state.set_state(CaseManagement.viewing_selecting_owner_type)
        await message.answer("لطفاً نوع مالک پرونده را انتخاب کنید:", reply_markup=kb_case_owner_type_inline("view"))
        return

    license_code = user.get("license_code")
    page = 1
    limit = 10
    offset = (page - 1) * limit
    
    cases = db.get_all_cases(db_path, license_code, limit=limit, offset=offset)
    total_cases = db.count_all_cases(db_path, license_code)
    total_pages = (total_cases + limit - 1) // limit
    
    if not cases:
        await message.answer("❌ هیچ پرونده‌ای وجود ندارد.")
        return
    
    await message.answer(
        "📂 پرونده مورد نظر را برای مشاهده جزئیات انتخاب کنید:", 
        reply_markup=kb_case_selection(cases, page=page, total_pages=total_pages)
    )


@router.callback_query(CaseManagement.viewing_selecting_owner_type, F.data.startswith("view_type_"))
async def handle_view_owner_type(callback: CallbackQuery, state: FSMContext, db_path: str):
    owner_type = callback.data.replace("view_type_", "")
    await state.update_data(view_owner_type=owner_type)
    
    from .keyboards import kb_agency_selection, kb_client_license_selection
    all_lics = db.get_all_licenses(db_path)
    
    if owner_type == "agency":
        agencies = [l for l in all_lics if l["license_type"] == "agency"]
        await state.set_state(CaseManagement.viewing_selecting_agency)
        await callback.message.edit_text("🏢 لیست موسسات را انتخاب کنید:", reply_markup=kb_agency_selection(agencies, "view_lic"))
    elif owner_type == "blogger":
        bloggers = [l for l in all_lics if l["license_type"] == "blogger"]
        await state.set_state(CaseManagement.viewing_selecting_agency)
        await callback.message.edit_text("🤳 لیست بلاگرها را انتخاب کنید:", reply_markup=kb_agency_selection(bloggers, "view_lic"))
    else:
        clients = [l for l in all_lics if l["license_type"] == "direct_client"]
        await state.set_state(CaseManagement.viewing_selecting_client)
        await callback.message.edit_text("👤 لیست کلاینت‌های مستقیم را انتخاب کنید:", reply_markup=kb_client_license_selection(clients, "view_lic"))


@router.callback_query(F.data == "view_back_to_type")
async def handle_view_back_to_type(callback: CallbackQuery, state: FSMContext):
    from .keyboards import kb_case_owner_type_inline
    await state.set_state(CaseManagement.viewing_selecting_owner_type)
    await callback.message.edit_text("لطفاً نوع مالک پرونده را انتخاب کنید:", reply_markup=kb_case_owner_type_inline("view"))


@router.callback_query(F.data.startswith("view_lic_"))
async def handle_view_license_selected(callback: CallbackQuery, state: FSMContext, db_path: str):
    license_code = callback.data.replace("view_lic_", "")
    await state.update_data(view_license_code=license_code)
    
    page = 1
    limit = 10
    offset = (page - 1) * limit
    
    cases = db.get_all_cases(db_path, license_code, limit=limit, offset=offset)
    total_cases = db.count_all_cases(db_path, license_code)
    total_pages = (total_cases + limit - 1) // limit
    
    if not cases:
        await callback.message.edit_text("❌ هیچ پرونده‌ای برای این لایسنس یافت نشد.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 بازگشت", callback_data="view_back_to_type")]]))
        return
    
    await callback.message.edit_text(
        "📂 پرونده مورد نظر را برای مشاهده جزئیات انتخاب کنید:", 
        reply_markup=kb_case_selection(cases, prefix="case_view_", page=page, total_pages=total_pages)
    )


@router.callback_query(F.data.startswith("cases_page_"))
async def handle_cases_pagination(callback: CallbackQuery, state: FSMContext, db_path: str):
    await callback.answer()
    page = int(callback.data.replace("cases_page_", ""))
    
    data = await state.get_data()
    license_code = data.get("view_license_code")
    
    if not license_code:
        user = db.get_user(db_path, callback.from_user.id)
        license_code = user.get("license_code") if user else None
    
    limit = 10
    offset = (page - 1) * limit
    
    cases = db.get_all_cases(db_path, license_code, limit=limit, offset=offset)
    total_cases = db.count_all_cases(db_path, license_code)
    total_pages = (total_cases + limit - 1) // limit
    
    await callback.message.edit_text(
        "📂 پرونده مورد نظر را برای مشاهده جزئیات انتخاب کنید:",
        reply_markup=kb_case_selection(cases, page=page, total_pages=total_pages)
    )


@router.callback_query(F.data == "ignore")
async def handle_ignore_callback(callback: CallbackQuery):
    await callback.answer()


async def _notify_case_owner_interview_deleted(bot: Bot, db_path: str, interview: dict, reason_text: str | None = None):
    try:
        case_id = interview.get('case_id')
        if not case_id:
            return
        case = db.get_case(db_path, case_id)
        if not case:
            return
        license_code = case.get('owner_license_code')
        if not license_code:
            return

        members = db.get_users_by_license(db_path, license_code)
        if not members:
            return

        company = interview.get('company_name') or 'نامشخص'
        scheduled = interview.get('scheduled_at_iso') or '-'
        base_text = (
            f"❌ مصاحبه شما لغو شد.\n\n"
            f"🏢 شرکت: {company}\n"
            f"📅 زمان: {scheduled}\n"
            f"🧾 پرونده: {case_id}"
        )
        if reason_text:
            base_text += f"\n\n📌 دلیل لغو: {reason_text}"

        for m in members:
            try:
                await bot.send_message(m['user_id'], base_text)
            except Exception as e:
                print(f"[WARN] Failed to notify interview cancellation to {m.get('user_id')}: {e}")
    except Exception as e:
        print(f"[WARN] _notify_case_owner_interview_deleted failed: {e}")


@router.callback_query(F.data.startswith("case_view_"))
async def handle_case_view_callback(callback: CallbackQuery, db_path: str):
    await callback.answer()
    case_id = callback.data.replace("case_view_", "")
    case = db.get_case(db_path, case_id)
    if not case:
        await callback.message.edit_text("❌ پرونده یافت نشد.")
        return

    # Check if the institution is special (REMOVED)
    special_header = ""

    status_text = get_status_display(case.get("status"), case.get("yellow_reason"))

    interviews = db.get_interviews(db_path, case_id)
    iv_count = len(interviews)
    
    installments = db.get_installments(db_path, case_id)
    inst_text = ""
    if installments:
        parts = []
        for i in installments:
            amount_str = format_amount(i['amount'])
            status_tag = ""
            if i.get('is_paid'):
                status_tag = " (پرداخت شد ✔)"
            
            idx_word = {1: "اول", 2: "دوم", 3: "سوم", 4: "چهارم", 5: "پنجم", 6: "ششم"}.get(i['idx'], f"{i['idx']}")
            parts.append(f"قسط {idx_word}: {amount_str}{status_tag}")
        
        inst_text = "💰 مبالغ اقساط: " + " | ".join(parts)
    
    # Detailed fields info
    fields = db.get_case_fields(db_path, case_id)
    fields_text = ""
    for f in fields:
        status_emoji = "🔴" if f['status'] == 'red' else "🟡" if f['status'] == 'yellow' else "🟢"
        fields_text += f"\n🎓 {f['field_name']}\n      وضعیت: {status_emoji} | درخواست: {f['requests_count']} | جلسات: {f['presentations_count']}"
        if f['status'] == 'yellow' and f['yellow_reason']:
            fields_text += f"\n      ⚠️ علت زرد: {f['yellow_reason']}"

    # New file status
    file_status_text = ""
    if case.get("employer_contract_file_id"):
        file_status_text += "\n✅ قرارداد کارفرما: موجود"
    if case.get("pre_approval_file_id"):
        file_status_text += "\n✅ پیش‌تاییدیه: موجود"

    text = (
        f"{special_header}"
        f"📋 جزئیات پرونده: {case_id}\n"
        f"👤 کلاینت: {case['client_name']}\n"
        f"💼 نوع مالک: {'موسسه' if case['owner_type'] == 'agency' else 'کلاینت مستقیم'}\n"
        f"🏢 لایسنس: `{case['owner_license_code']}`\n"
        f"💰 مبلغ کل: {format_amount(case['total_amount'])}\n"
        f"📊 اقساط: {case['installments_count']}\n"
        f"{inst_text}\n"
        f"✈️ نوع ویزا: {case['field_of_study'] or '-'}\n"
        f"📅 تعداد مصاحبه‌ها: {iv_count}\n"
        f"📌 وضعیت کلی: {status_text}\n"
        f"{file_status_text}\n"
        f"━━━━━━━━━━━━━━\n"
        f"{fields_text}\n"
        f"━━━━━━━━━━━━━━\n"
    )
    from .keyboards import kb_case_detail
    user_db = db.get_user(db_path, callback.from_user.id)
    is_super_admin = user_db["role"] == "super_admin" if user_db else False
    is_admin = user_db["role"] in ("admin", "super_admin") if user_db else False
    is_active = bool(case.get("is_active", True))
    
    has_employer_contract = bool(case.get("employer_contract_file_id"))
    has_pre_approval = bool(case.get("pre_approval_file_id"))
    
    # Add comments if user is super_admin
    comment_text = ""
    if is_super_admin:
        comments = db.get_case_comments(db_path, case_id)
        if comments:
            comment_text = "\n\n━━━━━━━━━━━━━━\n💬 یادداشت‌های مدیریت:"
            for c in comments:
                visibility = "🔒" if c['is_private'] else "📢"
                read_status = "✅" if c['is_read'] else "⏳"
                file_icon = "📎" if c['file_id'] else ""
                
                comment_text += (
                    f"\n{visibility} {c['comment_text']} {file_icon}\n"
                    f"└ {read_status} وضعیت: { 'خوانده شده' if c['is_read'] else 'در انتظار' }\n"
                    f"└ ویرایش: /edit_comment_{c['id']} | حذف: /del_comment_{c['id']}\n"
                )
            comment_text += "━━━━━━━━━━━━━━"

    await callback.message.edit_text(text + comment_text, parse_mode="Markdown", reply_markup=kb_case_detail(case_id, is_admin=is_admin, is_active=is_active, is_super_admin=is_super_admin, has_employer_contract=has_employer_contract, has_pre_approval=has_pre_approval))


@router.callback_query(F.data.startswith("delete_interview_target_"))
async def handle_delete_interview_target(callback: CallbackQuery, state: FSMContext, db_path: str):
    interview_id = int(callback.data.replace("delete_interview_target_", ""))
    
    user = db.get_user(db_path, callback.from_user.id)
    if not user:
        return

    interview = db.get_interview(db_path, interview_id)
    if not interview:
        await callback.answer("❌ مصاحبه یافت نشد.", show_alert=True)
        return

    # For non-admin users, check if they own this interview (by case ownership)
    if user["role"] not in ("super_admin", "admin"):
        case = db.get_case(db_path, interview['case_id'])
        if not case or case.get('owner_license_code') != user.get('license_code'):
            await callback.answer("❌ شما فقط می‌توانید مصاحبه‌های خودتان را حذف کنید.", show_alert=True)
            return

    await state.update_data(interview_id=interview_id)
    await state.set_state(InterviewManagement.confirming_interview_delete)

    from .keyboards import kb_yes_no
    await callback.message.edit_text(
        "⚠️ آیا از حذف این مصاحبه اطمینان دارید؟\n\nاین عملیات غیرقابل بازگشت است.",
        reply_markup=kb_yes_no(f"interview_del_{interview_id}")
    )
    await callback.answer()


@router.callback_query(F.data.startswith("delete_interview_apology_"))
async def delete_interview_apology_start(callback: CallbackQuery, state: FSMContext, db_path: str):
    user = db.get_user(db_path, callback.from_user.id)
    if not user:
        return

    if user.get("role") != "super_admin":
        await callback.answer("❌ این عملیات فقط برای سوپر ادمین امکان‌پذیر است.", show_alert=True)
        return

    interview_id = int(callback.data.replace("delete_interview_apology_", ""))
    await state.update_data(interview_id=interview_id)
    await state.set_state(InterviewManagement.asking_apology_reason)

    from .keyboards import kb_apology_reason_selection
    await callback.message.edit_text(
        "🤔 آیا برای حذف این مصاحبه دلیل خاصی دارید؟",
        reply_markup=kb_apology_reason_selection(interview_id)
    )
    await callback.answer()


@router.callback_query(InterviewManagement.asking_apology_reason, F.data.startswith("apology_reason_cancel_"))
async def apology_reason_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ عملیات لغو شد.")
    await callback.answer()


@router.callback_query(InterviewManagement.asking_apology_reason, F.data.startswith("apology_reason_no_"))
async def apology_reason_no(callback: CallbackQuery, state: FSMContext, bot: Bot, db_path: str):
    interview_id = int(callback.data.replace("apology_reason_no_", ""))

    user = db.get_user(db_path, callback.from_user.id)
    if not user or user.get("role") != "super_admin":
        await callback.answer("❌ عدم دسترسی", show_alert=True)
        return

    iv = db.get_interview(db_path, interview_id)
    if not iv:
        await callback.answer("❌ مصاحبه یافت نشد.", show_alert=True)
        await state.clear()
        return

    db.delete_interview(db_path, interview_id)
    await _notify_case_owner_interview_deleted(bot, db_path, iv, reason_text=None)

    await callback.message.edit_text("✅ مصاحبه با موفقیت حذف شد و به کاربر اطلاع‌رسانی شد.")
    await state.clear()
    await callback.answer()


@router.callback_query(InterviewManagement.asking_apology_reason, F.data.startswith("apology_reason_yes_"))
async def apology_reason_yes(callback: CallbackQuery, state: FSMContext):
    interview_id = int(callback.data.replace("apology_reason_yes_", ""))
    await state.update_data(interview_id=interview_id)
    await state.set_state(InterviewManagement.entering_apology_reason_text)
    await callback.message.edit_text("📝 لطفاً دلیل لغو/حذف این مصاحبه را بنویسید:")
    await callback.answer()


@router.message(InterviewManagement.entering_apology_reason_text)
async def apology_reason_text_entered(message: Message, state: FSMContext, bot: Bot, db_path: str):
    user = db.get_user(db_path, message.from_user.id)
    if not user or user.get("role") != "super_admin":
        await message.answer("❌ این عملیات فقط برای سوپر ادمین امکان‌پذیر است.")
        await state.clear()
        return

    data = await state.get_data()
    interview_id = data.get("interview_id")
    reason_text = (message.text or "").strip()
    if not interview_id:
        await message.answer("❌ خطای سیستمی: مصاحبه مشخص نیست.")
        await state.clear()
        return

    iv = db.get_interview(db_path, int(interview_id))
    if not iv:
        await message.answer("❌ مصاحبه یافت نشد.")
        await state.clear()
        return

    db.delete_interview(db_path, int(interview_id))
    await _notify_case_owner_interview_deleted(bot, db_path, iv, reason_text=reason_text)
    await message.answer("✅ مصاحبه حذف شد و پیام لغو به کاربر ارسال شد.")
    await state.clear()


@router.callback_query(F.data.startswith("delete_interview_"))
async def delete_interview_request(callback: CallbackQuery, state: FSMContext, db_path: str):
    user = db.get_user(db_path, callback.from_user.id)
    if not user:
        return

    interview_id = int(callback.data.replace("delete_interview_", ""))
    interview = db.get_interview(db_path, interview_id)
    if not interview:
        await callback.answer("❌ مصاحبه یافت نشد.", show_alert=True)
        return

    # For non-admin users, check if they own this interview (by case ownership)
    if user["role"] not in ("super_admin", "admin"):
        case = db.get_case(db_path, interview['case_id'])
        if not case or case.get('owner_license_code') != user.get('license_code'):
            await callback.answer("❌ شما فقط می‌توانید مصاحبه‌های خودتان را حذف کنید.", show_alert=True)
            return

    await state.update_data(interview_id=interview_id)
    await state.set_state(InterviewManagement.confirming_interview_delete)

    from .keyboards import kb_yes_no
    await callback.message.edit_text(
        "⚠️ آیا از حذف این مصاحبه اطمینان دارید؟\n\nاین عملیات غیرقابل بازگشت است.",
        reply_markup=kb_yes_no(f"interview_del_{interview_id}")
    )
    await callback.answer()


@router.callback_query(F.data.startswith("confirm_interview_del_"))
async def delete_interview_confirm(callback: CallbackQuery, state: FSMContext, bot: Bot, db_path: str):
    data = callback.data
    if data.endswith("_no"):
        await callback.message.edit_text("❌ عملیات لغو شد.")
        await state.clear()
        await callback.answer()
        return

    interview_id = int(data.replace("confirm_interview_del_", "").replace("_yes", ""))
    iv = db.get_interview(db_path, interview_id)
    if not iv:
        await callback.answer("❌ مصاحبه یافت نشد.", show_alert=True)
        await state.clear()
        return

    user = db.get_user(db_path, callback.from_user.id)
    if not user:
        return

    # Keep same permission check as request
    if user["role"] not in ("super_admin", "admin"):
        case = db.get_case(db_path, iv['case_id'])
        if not case or case.get('owner_license_code') != user.get('license_code'):
            await callback.answer("❌ عدم دسترسی", show_alert=True)
            await state.clear()
            return

    db.delete_interview(db_path, interview_id)

    # Notify case owner only if admin/super_admin deleted
    if user["role"] in ("super_admin", "admin"):
        await _notify_case_owner_interview_deleted(bot, db_path, iv, reason_text=None)

    await callback.message.edit_text("✅ مصاحبه حذف شد.")
    await state.clear()
    await callback.answer()


@router.callback_query(F.data == "back_to_cases_menu")
async def back_to_cases_menu_callback(callback: CallbackQuery, db_path: str):
    await callback.answer()
    user = db.get_user(db_path, callback.from_user.id)
    license_code = user.get("license_code") if user else None
    
    page = 1
    limit = 10
    offset = (page - 1) * limit
    
    cases = db.get_all_cases(db_path, license_code, limit=limit, offset=offset)
    total_cases = db.count_all_cases(db_path, license_code)
    total_pages = (total_cases + limit - 1) // limit
    
    await callback.message.edit_text(
        "📂 لیست پرونده‌ها:", 
        reply_markup=kb_case_selection(cases, page=page, total_pages=total_pages)
    )


@router.callback_query(F.data.startswith("case_empl_contract_"))
async def case_employer_contract_upload(callback: CallbackQuery, state: FSMContext, db_path: str):
    case_id = callback.data.replace("case_empl_contract_", "")
    await state.update_data(current_case_id=case_id, upload_type="employer_contract")
    await state.set_state(CaseManagement.waiting_for_employer_contract)
    await callback.message.answer("📜 لطفاً فایل قرارداد کارفرما را ارسال کنید:")
    await callback.answer()

@router.callback_query(F.data.startswith("case_pre_appr_"))
async def case_pre_approval_upload(callback: CallbackQuery, state: FSMContext, db_path: str):
    case_id = callback.data.replace("case_pre_appr_", "")
    await state.update_data(current_case_id=case_id, upload_type="pre_approval")
    await state.set_state(CaseManagement.waiting_for_pre_approval)
    await callback.message.answer("📜 لطفاً فایل پیش‌تاییدیه را ارسال کنید:")
    await callback.answer()

@router.message(CaseManagement.waiting_for_employer_contract, F.document | F.photo)
@router.message(CaseManagement.waiting_for_pre_approval, F.document | F.photo)
async def handle_new_file_upload(message: Message, state: FSMContext, bot: Bot, db_path: str, cfg):
    data = await state.get_data()
    case_id = data["current_case_id"]
    upload_type = data["upload_type"]
    
    file_id = message.document.file_id if message.document else message.photo[-1].file_id
    db.update_case_file(db_path, case_id, upload_type, file_id)
    
    # Find mapped installment and create pending reminder
    mapped_insts = db.get_mapped_installments(db_path, case_id, "contract" if upload_type == "employer_contract" else "pre_approval")
    
    for inst in mapped_insts:
        if not inst.get("is_paid", False):  # Add safety check for 'is_paid'
            db.add_pending_reminder(db_path, case_id, inst["id"], "contract" if upload_type == "employer_contract" else "pre_approval")
            
    await message.answer(f"✅ فایل با موفقیت ثبت شد و یادآوری اقساط مربوطه فعال گردید.")
    await state.clear()
    
    # Return to case view
    from .handlers import handle_case_view_callback
    class FakeCallback:
        def __init__(self, message, user, data):
            self.message = message
            self.from_user = user
            self.data = data
        async def answer(self): pass
    await handle_case_view_callback(FakeCallback(message, message.from_user, f"case_view_{case_id}"), db_path)

@router.callback_query(F.data.startswith("view_empl_contract_"))
async def view_employer_contract(callback: CallbackQuery, db_path: str, bot: Bot):
    case_id = callback.data.replace("view_empl_contract_", "")
    case = db.get_case(db_path, case_id)
    if case and case.get("employer_contract_file_id"):
        await bot.send_document(callback.from_user.id, case["employer_contract_file_id"], caption="📜 قرارداد کارفرما")
    else:
        await callback.answer("❌ فایلی یافت نشد.")

@router.callback_query(F.data.startswith("view_pre_appr_"))
async def view_pre_approval(callback: CallbackQuery, db_path: str, bot: Bot):
    case_id = callback.data.replace("view_pre_appr_", "")
    case = db.get_case(db_path, case_id)
    if case and case.get("pre_approval_file_id"):
        await bot.send_document(callback.from_user.id, case["pre_approval_file_id"], caption="📜 پیش‌تاییدیه")
    else:
        await callback.answer("❌ فایلی یافت نشد.")

@router.callback_query(F.data.startswith("admin_paid_"))
async def admin_mark_paid(callback: CallbackQuery, db_path: str):
    parts = callback.data.split("_")
    inst_id = int(parts[2])
    reminder_id = int(parts[3])
    
    db.update_installment_payment(db_path, inst_id, 1)
    db.update_reminder_status(db_path, reminder_id, 0, is_completed=1)
    
    await callback.message.edit_text(callback.message.text + "\n\n✅ وضعیت قسط به «پرداخت شد» تغییر یافت.")
    await callback.answer("ثبت شد.")
async def handle_case_iv_history_callback(callback: CallbackQuery, db_path: str):
    await callback.answer()
    case_id = callback.data.replace("case_iv_history_", "")
    interviews = db.get_interviews(db_path, case_id)
    
    if not interviews:
        await callback.message.answer(f"📅 برای پرونده {case_id} هیچ مصاحبه‌ای ثبت نشده است.")
        return
        
    text = f"📜 تاریخچه مصاحبه‌های پرونده {case_id}:\n\n"
    for i, iv in enumerate(interviews, 1):
        date_str = iv.get('scheduled_at_iso') or 'نامشخص'
        company = iv.get('company_name') or 'نامشخص'
        status = iv.get('status') or 'ثبت شده'
        
        # Task 9: Show all details
        platform = iv.get('platform') or 'نامشخص'
        link = iv.get('meeting_link') or 'نامشخص'
        city = iv.get('city') or 'نامشخص'
        emp = iv.get('employer_name') or 'نامشخص'
        user = iv.get('username') or '-'
        passw = iv.get('password') or '-'
        
        f_res = iv.get('followup_result') or '-'
        f_notes = iv.get('followup_notes') or '-'
        
        # Get selected field
        extracted = json.loads(iv['extracted_json']) if iv.get('extracted_json') else {}
        selected_field = extracted.get('selected_field', '')
        field_suffix = f" ({selected_field})" if selected_field else ""

        text += (
            f"🔹 مصاحبه #{i}{field_suffix}\n"
            f"🏢 شرکت: {company}\n"
            f"📅 تاریخ: `{date_str}`\n"
            f"📍 وضعیت: {status}\n"
            f"👤 کارفرما: {emp}\n"
            f"🏙 شهر: {city}\n"
            f"💻 پلتفرم: {platform}\n"
            f"🔗 لینک: {link}\n"
            f"🔑 یوزر/پس: `{user}` / `{passw}`\n"
        )
        
        if f_res != '-':
            text += f"📝 نتیجه پیگیری: {f_res}\n"
        if f_notes != '-':
            text += f"💬 توضیحات: {f_notes}\n"
            
        text += f"-------------------\n"
    
    await callback.message.answer(text, parse_mode="Markdown")


@router.message(F.text == "➕ اضافه کردن پرونده")
async def add_case_start(message: Message, state: FSMContext):
    await state.set_state(CaseManagement.selecting_owner_type)
    await message.answer("پرونده برای کیست؟", reply_markup=kb_cases_owner_type())


@router.message(CaseManagement.selecting_owner_type, F.text.in_(["برای موسسه", "برای کلاینت", "برای بلاگر"]))
async def select_owner_type(message: Message, state: FSMContext, db_path: str):
    if "موسسه" in message.text:
        owner_type = "agency"
    elif "بلاگر" in message.text:
        owner_type = "blogger"
    else:
        owner_type = "direct_client"
        
    await state.update_data(owner_type=owner_type)
    
    all_lics = db.get_all_licenses(db_path)
    if owner_type == "agency":
        target_lics = [l for l in all_lics if l["license_type"] == "agency"]
        type_fa = "موسسه‌ای"
    elif owner_type == "blogger":
        target_lics = [l for l in all_lics if l["license_type"] == "blogger"]
        type_fa = "بلاگری"
    else:
        target_lics = [l for l in all_lics if l["license_type"] == "direct_client"]
        type_fa = "کلاینت مستقیم"

    if not target_lics:
        await message.answer(f"❌ هیچ لایسنس {type_fa} وجود ندارد. ابتدا لایسنس بسازید.")
        return
        
    await state.set_state(CaseManagement.selecting_agency)
    if owner_type == "agency":
        await message.answer("🏢 موسسه مورد نظر را انتخاب کنید:", reply_markup=kb_agency_selection(target_lics))
    elif owner_type == "blogger":
        await message.answer("🤳 بلاگر مورد نظر را انتخاب کنید:", reply_markup=kb_agency_selection(target_lics))
    else:
        await message.answer("👤 کلاینت مستقیم مورد نظر را انتخاب کنید:", reply_markup=kb_client_license_selection(target_lics))


@router.callback_query(CaseManagement.selecting_agency, F.data.startswith("select_owner_lic_"))
async def handle_owner_lic_selection(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    lic_code = callback.data.replace("select_owner_lic_", "")
    await state.update_data(selected_license=lic_code)
    await state.set_state(CaseManagement.entering_client_name)
    await callback.message.edit_text(f"✅ لایسنس {lic_code} انتخاب شد.\n\n👤 حالا نام کلاینت را وارد کنید:")


@router.callback_query(F.data == "back_to_owner_type")
async def back_to_owner_type_callback(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(CaseManagement.selecting_owner_type)
    await callback.message.delete()
    await callback.message.answer("پرونده برای کیست؟", reply_markup=kb_cases_owner_type())


@router.message(CaseManagement.entering_client_name)
async def enter_client_name(message: Message, state: FSMContext):
    await state.update_data(client_name=message.text.strip())
    await state.set_state(CaseManagement.entering_total_amount)
    await message.answer("مبلغ کل قرارداد را به یورو وارد کنید:")


@router.message(CaseManagement.entering_total_amount)
async def enter_total_amount(message: Message, state: FSMContext):
    try:
        amount = float(message.text.strip())
        await state.update_data(total_amount=amount)
        await state.set_state(CaseManagement.entering_installments_count)
        await message.answer("تعداد اقساط را وارد کنید:")
    except ValueError:
        await message.answer("لطفاً عدد وارد کنید:")


@router.message(CaseManagement.entering_installments_count)
async def enter_installments_count(message: Message, state: FSMContext):
    try:
        count = int(message.text.strip())
        await state.update_data(installments_count=count, current_installment=1, installments=[], installment_mappings={})
        await state.set_state(CaseManagement.entering_installment_amount)
        await message.answer(f"💰 مبلغ قسط 1 را به یورو وارد کنید:")
    except ValueError:
        await message.answer("❌ لطفاً عدد وارد کنید:")


@router.message(CaseManagement.entering_installment_amount)
async def enter_installment_amount(message: Message, state: FSMContext):
    try:
        amount = float(message.text.strip())
        data = await state.get_data()
        installments = data.get("installments", [])
        installments.append(amount)
        current = data.get("current_installment", 1)
        total = data.get("installments_count", 1)
        
        if current < total:
            await state.update_data(installments=installments, current_installment=current + 1)
            await message.answer(f"💰 مبلغ قسط {current + 1} را به یورو وارد کنید:")
        else:
            await state.update_data(installments=installments)
            await state.set_state(CaseManagement.mapping_installments)
            from .keyboards import kb_installment_mapping
            
            # Prepare installment list for mapping keyboard
            inst_list = [{"idx": i+1, "amount": a} for i, a in enumerate(installments)]
            await state.update_data(installments_list=inst_list)
            
            mapping = {} # Initial empty mapping
            await message.answer(
                f"🎯 حالا باید مشخص کنید هر قسط مربوط به کدام مرحله است.\n\n"
                f"تخصیص قسط شماره 1 ({installments[0]}€):",
                reply_markup=kb_installment_mapping(inst_list, 0, mapping)
            )
    except ValueError:
        await message.answer("❌ لطفاً عدد وارد کنید:")

@router.callback_query(CaseManagement.mapping_installments, F.data.startswith("map_toggle_"))
async def toggle_installment_mapping(callback: CallbackQuery, state: FSMContext, db_path: str):
    parts = callback.data.split("_")
    idx = int(parts[2])
    event = parts[3]
    
    # DEBUG LOG
    print(f"[DEBUG] Toggle Triggered: idx={idx}, event='{event}'")
    
    data = await state.get_data()
    mapping = data.get("installment_mappings")
    if not isinstance(mapping, dict):
        mapping = {}
    
    # Force key to be a string for consistency
    s_idx = str(idx)
    
    # Initialize list if not present
    if s_idx not in mapping or not isinstance(mapping[s_idx], list):
        mapping[s_idx] = []
    
    # Toggle logic: ensure exact string comparison
    current_list = list(mapping.get(s_idx, []))
    if event in current_list:
        mapping[s_idx] = [e for e in current_list if e != event]
        print(f"[DEBUG] Removed '{event}' from mapping[{s_idx}]")
    else:
        mapping[s_idx] = current_list + [event]
        print(f"[DEBUG] Added '{event}' to mapping[{s_idx}]")
        
    await state.update_data(installment_mappings=mapping)
    
    # Refresh data after update to ensure we have the latest mapping for KB and logic
    data = await state.get_data()
    mapping = data.get("installment_mappings", {})
    if not isinstance(mapping, dict):
        mapping = {}
        
    print(f"[DEBUG] Current mapping for {s_idx}: {mapping.get(s_idx)}")
        
    # Standardize mapping access for the rest of the function
    current_mapping = mapping.get(s_idx, [])
    
    # Handle reminders immediately if not paid for relevant event types
    if event in ("initial", "preapproval", "interview", "contract"):
        # In Edit mode, we need case_id and inst_id from state
        case_id = data.get("editing_mapping_case_id")
        inst_id = data.get("editing_mapping_inst_id")
        
        if case_id and inst_id:
             if event in current_mapping:
                 with db.connect(db_path) as conn:
                     exists = conn.execute("SELECT id FROM pending_reminders WHERE installment_id = ? AND reminder_type = ? AND is_completed = 0", (inst_id, event)).fetchone()
                     if not exists:
                         db.add_pending_reminder(db_path, case_id, inst_id, event)
             else:
                 with db.connect(db_path) as conn:
                     conn.execute("UPDATE pending_reminders SET is_completed = 1 WHERE installment_id = ? AND reminder_type = ?", (inst_id, event))
    
    from .keyboards import kb_installment_mapping
    inst_list = data.get("installments_list", [])
    current_idx = next((i for i, inst in enumerate(inst_list) if str(inst["idx"]) == s_idx), -1)
    
    if current_idx == -1:
        await callback.answer("❌ خطا در یافتن قسط.")
        return
        
    try:
        # Use mapping from state to ensure KB reflects what's stored
        await callback.message.edit_reply_markup(reply_markup=kb_installment_mapping(inst_list, current_idx, mapping))
    except Exception as e:
        if "message is not modified" not in str(e):
            raise e
    await callback.answer()

@router.callback_query(F.data.startswith("inst_map_"))
async def handle_installment_map_callback(callback: CallbackQuery, state: FSMContext, db_path: str):
    parts = callback.data.replace("inst_map_", "").split("_")
    inst_id = int(parts[0])
    case_id = parts[1]
    
    # Get the specific installment from DB
    with db.connect(db_path) as conn:
        row = conn.execute("SELECT * FROM installments WHERE id = ?", (inst_id,)).fetchone()
        if not row:
            await callback.answer("❌ قسط یافت نشد.")
            return
        inst = dict(row)
    
    # Prepare mapping for the keyboard
    events = []
    if inst.get('is_for_initial'): events.append("initial")
    if inst.get('is_for_interview'): events.append("interview")
    if inst.get('is_for_contract'): events.append("contract")
    if inst.get('is_for_preapproval'): events.append("preapproval")
    
    mapping = {str(inst['idx']): events}
    inst_list = [{"idx": inst['idx'], "amount": inst['amount']}]
    
    await state.update_data(
        editing_mapping_case_id=case_id,
        editing_mapping_inst_id=inst_id,
        editing_mapping_idx=inst['idx'],
        installment_mappings=mapping,
        installments_list=inst_list
    )
    
    await state.set_state(CaseManagement.mapping_installments)
    
    from .keyboards import kb_installment_mapping
    await callback.message.edit_text(
        f"🎯 ویرایش تخصیص قسط شماره {inst['idx']} ({inst['amount']}€):",
        reply_markup=kb_installment_mapping(inst_list, 0, mapping)
    )
    await callback.answer()

@router.callback_query(CaseManagement.mapping_installments, F.data.startswith("map_next_"))
async def next_installment_mapping(callback: CallbackQuery, state: FSMContext, db_path: str):
    data = await state.get_data()
    
    # Check if we are in EDIT mode
    if "editing_mapping_inst_id" in data:
        case_id = data["editing_mapping_case_id"]
        inst_id = data["editing_mapping_inst_id"]
        idx = data["editing_mapping_idx"]
        mapping = data.get("installment_mappings", {})
        events = mapping.get(str(idx), mapping.get(idx, []))
        
        # Clear existing mappings for this installment first
        for event in ["interview", "contract", "preapproval", "initial"]:
            db.update_installment_mapping(db_path, inst_id, event, 0)
            
        # Apply new ones
        for event in events:
            db.update_installment_mapping(db_path, inst_id, event, 1)
            
        # If it's the initial payment (at contract signing), trigger the reminder immediately if not paid
        if "initial" in events:
            # Check if already has a pending reminder to avoid duplicates
            with db.connect(db_path) as conn:
                exists = conn.execute("SELECT id FROM pending_reminders WHERE installment_id = ? AND reminder_type = 'initial' AND is_completed = 0", (inst_id,)).fetchone()
                if not exists:
                    db.add_pending_reminder(db_path, case_id, inst_id, "initial")
        else:
            # If initial was removed, mark pending initial reminders as completed
            with db.connect(db_path) as conn:
                conn.execute("UPDATE pending_reminders SET is_completed = 1 WHERE installment_id = ? AND reminder_type = 'initial'", (inst_id,))
            
        await state.clear()
        await callback.answer("✅ تخصیص قسط بروزرسانی شد.")
        
        # Return to installment management
        installments = db.get_installments(db_path, case_id)
        from .keyboards import kb_installment_management
        await callback.message.edit_text(
            f"💰 مدیریت اقساط پرونده {case_id}\n\nبرای تغییر وضعیت پرداخت هر قسط روی آن کلیک کنید:",
            reply_markup=kb_installment_management(case_id, installments)
        )
        return

    # CREATE mode logic
    idx = int(callback.data.split("_")[2])
    total = data["installments_count"]
    
    if idx < total:
        new_idx = idx + 1
        installments = data["installments"]
        mapping = data.get("installment_mappings", {})
        inst_list = data["installments_list"]
        
        from .keyboards import kb_installment_mapping
        await callback.message.edit_text(
            f"🎯 تخصیص قسط شماره {new_idx} ({installments[new_idx-1]}€):",
            reply_markup=kb_installment_mapping(inst_list, new_idx-1, mapping)
        )
    else:
        await state.set_state(CaseManagement.entering_field_of_study)
        await callback.message.edit_text("🎓 رشته تحصیلی/شغلی را وارد کنید:")
    await callback.answer()


@router.message(CaseManagement.entering_field_of_study)
async def enter_field(message: Message, state: FSMContext):
    field = message.text.strip()
    data = await state.get_data()
    fields = data.get("fields", [])
    fields.append(field)
    await state.update_data(fields=fields)
    await state.set_state(CaseManagement.adding_fields)
    await message.answer(f"✅ رشته «{field}» ثبت شد.\nآیا می‌خواهید رشته دیگری اضافه کنید؟", reply_markup=kb_add_more_fields())


@router.callback_query(CaseManagement.adding_fields, F.data == "field_add_more")
async def add_more_fields(callback: CallbackQuery, state: FSMContext):
    await state.set_state(CaseManagement.entering_field_of_study)
    await callback.message.answer("رشته بعدی را وارد کنید:")
    await callback.answer()


@router.callback_query(CaseManagement.adding_fields, F.data == "field_finish_adding")
async def finish_adding_fields(callback: CallbackQuery, state: FSMContext):
    await state.set_state(CaseManagement.entering_visa_type)
    await callback.message.answer("نوع ویزا را انتخاب کنید (می‌توانید چند مورد را انتخاب کنید):", reply_markup=kb_visa_types())
    await callback.answer()


@router.callback_query(F.data.startswith("visa_toggle_"))
async def toggle_visa(callback: CallbackQuery, state: FSMContext):
    visa_type = callback.data.replace("visa_toggle_", "")
    data = await state.get_data()
    selected_visas = data.get("selected_visas", [])

    if visa_type in selected_visas:
        selected_visas.remove(visa_type)
    else:
        selected_visas.append(visa_type)

    await state.update_data(selected_visas=selected_visas)
    await callback.message.edit_reply_markup(reply_markup=kb_visa_types(selected_visas))
    await callback.answer()


@router.callback_query(F.data == "visa_confirm")
async def confirm_visa(callback: CallbackQuery, state: FSMContext, bot: Bot, db_path: str):
    data = await state.get_data()
    selected_visas = data.get("selected_visas", [])
    
    if not selected_visas:
        await callback.answer("لطفاً حداقل یک نوع ویزا انتخاب کنید.", show_alert=True)
        return

    visa_type_str = " ، ".join(selected_visas)
    case_id = f"CASE-{gen_license_code(6)}"
    
    try:
        db.create_case(
            db_path, case_id, data["owner_type"], data.get("selected_license", ""),
            data["client_name"], data["total_amount"], data["installments_count"],
            data.get("fields", []), visa_type_str
        )
        db.add_installments(db_path, case_id, data["installments"])
        
        # Save installment mappings
        mapping = data.get("installment_mappings", {})
        installments_from_db = db.get_installments(db_path, case_id)
        for idx_str, events in mapping.items():
            idx = int(idx_str)
            # Find the installment ID from DB for this idx
            inst_obj = next((i for i in installments_from_db if i["idx"] == idx), None)
            if inst_obj:
                for event in events:
                    db.update_installment_mapping(db_path, inst_obj["id"], event, 1)
                    # Trigger initial payment reminder if mapped
                    if event == "initial":
                        db.add_pending_reminder(db_path, case_id, inst_obj["id"], "initial")
        
        try:
            await callback.message.delete()
        except:
            pass
            
        await callback.message.answer(f"✅ پرونده ساخته شد:\nکد: {case_id}\nکلاینت: {data['client_name']}", reply_markup=kb_cases_menu())
        
        # Notify users associated with the license
        lic_code = data.get("selected_license")
        if lic_code:
            users_to_notify = db.get_users_by_license(db_path, lic_code)
            
            notification_text = (
                f"🔔 پرونده جدید ثبت شد\n\n"
                f"پرونده «{data['client_name']}» با مشخصات زیر در مجموعه ایران آوسبیلدونگ ثبت شد:\n"
                f"• کد پرونده: {case_id}\n"
                f"• رشته: {data['field_of_study']}\n"
                f"• نوع ویزا: {visa_type_str}\n\n"
                f"جهت مشاهده جزئیات بیشتر به بخش «👁 مشاهده پرونده‌ها» مراجعه کنید. ✨"
            )
            
            for user in users_to_notify:
                try:
                    await bot.send_message(user["user_id"], notification_text)
                except Exception as e:
                    print(f"Error notifying user {user['user_id']}: {e}")

        await state.clear()
    except Exception as e:
        import traceback
        logger.error(f"Error in confirm_visa: {e}\n{traceback.format_exc()}")
        await callback.answer(f"خطا در ثبت پرونده: {e}", show_alert=True)


@router.message(CaseManagement.entering_visa_type)
async def enter_visa_manual(message: Message):
    await message.answer("لطفاً از دکمه‌های بالا برای انتخاب نوع ویزا استفاده کنید.")


@router.message(F.text == "🔓 تیکت‌های باز")
async def open_tickets(message: Message, db_path: str):
    user = db.get_user(db_path, message.from_user.id)
    if user["role"] in ("super_admin", "admin"):
        tickets = db.get_all_tickets(db_path, status="open")
        if not tickets:
            await message.answer("✅ هیچ تیکت باز و پاسخ‌نداده‌ای وجود ندارد.")
            return
        await message.answer("🎫 لیست تیکت‌های باز مدیریت:\n\nبرای مشاهده جزئیات و پاسخ‌دهی انتخاب کنید:", reply_markup=kb_open_tickets_list(tickets))
    else:
        tickets = db.get_all_tickets(db_path, user_id=message.from_user.id, status="open")
        if not tickets:
            await message.answer("هیچ تیکت بازی ندارید.")
            return
        text = "🎫 تیکت‌های باز شما:\n\n"
        for t in tickets[:10]:
            text += f"#{t['id']} - {t['subject'] or 'بدون موضوع'}\n"
        await message.answer(text, reply_markup=kb_tickets_menu())

@router.callback_query(F.data.startswith("ticket_view_"))
@router.callback_query(F.data.startswith("view_ticket_"))
async def ticket_view(callback: CallbackQuery, db_path: str):
    data = callback.data
    if data.startswith("ticket_view_"):
        ticket_id = int(data.replace("ticket_view_", ""))
    else:
        ticket_id = int(data.replace("view_ticket_", ""))
    
    ticket = db.get_ticket(db_path, ticket_id)
    if not ticket:
        await callback.answer("تیکت یافت نشد.")
        return
    
    msgs = db.get_ticket_messages(db_path, ticket_id)
    text = f"🎫 شماره تیکت: #{ticket_id}\n"
    text += f"👤 از: {ticket['created_by_role']}\n"
    text += f"📝 موضوع: {ticket['subject'] or 'بدون موضوع'}\n"
    text += "━" * 15 + "\n"
    
    for m in msgs:
        role_label = "👤 کاربر" if m['sender_role'] in ('agency', 'direct_client') else "👨‍💻 ادمین"
        safe_text = (m['text'] or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        text += f"{role_label}: {safe_text}\n"
    
    if ticket['assigned_admin_id']:
        admin = db.get_user(db_path, ticket['assigned_admin_id'])
        admin_name = admin.get('full_name') or f"ID: {ticket['assigned_admin_id']}"
        text += f"\n⚠️ این تیکت توسط <b>{admin_name}</b> در حال پیگیری است."

    await callback.message.answer(text, reply_markup=kb_ticket_actions(ticket_id), parse_mode="HTML")
    await callback.answer()


@router.message(F.text == "📦 آرشیو تیکت‌ها")
async def closed_tickets(message: Message, db_path: str):
    user = db.get_user(db_path, message.from_user.id)
    if user["role"] in ("super_admin", "admin"):
        tickets = db.get_all_tickets(db_path, status="closed")
    else:
        tickets = db.get_all_tickets(db_path, user_id=message.from_user.id, status="closed")
    
    if not tickets:
        await message.answer("📁 در حال حاضر هیچ تیکتی در آرشیو وجود ندارد.")
        return

    text = "📁 آرشیو تیکت‌های بسته\n\nتیکت مورد نظر را برای مشاهده تاریخچه انتخاب کنید:"
    
    buttons = []
    # Show last 10 for simplicity
    for t in tickets[:10]:
        date_str = t['created_at'].split('T')[0] if 'T' in t['created_at'] else t['created_at']
        buttons.append([InlineKeyboardButton(text=f"🎫 #{t['id']} | {t['subject'] or 'بدون موضوع'} ({date_str})", callback_data=f"view_ticket_{t['id']}")])
    
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="Markdown")


@router.message(F.text == "➕ ثبت مصاحبه جدید")
async def new_interview_start(message: Message, state: FSMContext, db_path: str):
    user = db.get_user(db_path, message.from_user.id)
    if not user:
        return

    if user["role"] in ("super_admin", "admin"):
        await state.update_data(action="create")
        await state.set_state(InterviewManagement.selecting_owner_type)
        from .keyboards import kb_interview_owner_type
        await message.answer("📅 ثبت مصاحبه جدید\n\nلطفاً نوع پرونده را انتخاب کنید:", reply_markup=kb_interview_owner_type())
    else:
        # Agency or Direct Client - only show their own cases
        license_code = user.get("license_code")
        if not license_code:
            await message.answer("❌ شما لایسنس فعالی ندارید.")
            return
            
        cases = db.get_all_cases(db_path, license_code)
        if not cases:
            await message.answer("❌ هیچ پرونده‌ای یافت نشد.")
            return
            
        await state.set_state(InterviewManagement.selecting_case)
        await message.answer("📅 پرونده مورد نظر را انتخاب کنید:", reply_markup=kb_case_selection(cases, prefix="case_interview_"))


@router.message(F.text == "👁 مشاهده مصاحبه‌ها")
async def view_interviews_start(message: Message, state: FSMContext, db_path: str):
    user = db.get_user(db_path, message.from_user.id)
    if not user:
        return

    if user["role"] in ("super_admin", "admin"):
        await state.update_data(action="view")
        await state.set_state(InterviewManagement.selecting_owner_type)
        from .keyboards import kb_interview_owner_type
        await message.answer("👁 مشاهده مصاحبه‌ها\n\nلطفاً نوع پرونده را انتخاب کنید:", reply_markup=kb_interview_owner_type())
    else:
        await view_interviews(message, db_path)


@router.message(F.text == "🗑 حذف مصاحبه")
async def delete_interview_menu_start(message: Message, state: FSMContext, db_path: str):
    user = db.get_user(db_path, message.from_user.id)
    if not user:
        return

    # Check permission
    if user["role"] not in ("super_admin", "admin"):
        # For regular users, we don't usually show this button in menu, but safety check:
        await message.answer("❌ شما دسترسی به این بخش را ندارید.")
        return

    await state.update_data(action="delete")
    await state.set_state(InterviewManagement.selecting_owner_type)
    from .keyboards import kb_interview_owner_type
    await message.answer("🗑 حذف مصاحبه\n\nلطفاً نوع پرونده را انتخاب کنید تا لیست مصاحبه‌های آن را ببینید:", reply_markup=kb_interview_owner_type())

@router.message(InterviewManagement.selecting_owner_type, F.text == "موسسات")
async def view_interviews_agencies(message: Message, state: FSMContext, db_path: str):
    agencies = db.get_all_agencies(db_path)
    if not agencies:
        await message.answer("❌ هیچ موسسه‌ای یافت نشد.")
        return
    await state.set_state(InterviewManagement.selecting_agency)
    await message.answer("🏢 موسسه مورد نظر را انتخاب کنید:", reply_markup=kb_agency_selection(agencies))

@router.message(InterviewManagement.selecting_owner_type, F.text == "کلاینت ها")
async def view_interviews_clients(message: Message, state: FSMContext, db_path: str):
    clients = db.get_all_direct_clients(db_path)
    if not clients:
        await message.answer("❌ هیچ کلاینت مستقیمی یافت نشد.")
        return
    await state.set_state(InterviewManagement.selecting_client)
    await message.answer("👤 کلاینت مورد نظر را انتخاب کنید:", reply_markup=kb_client_license_selection(clients))


@router.callback_query(InterviewManagement.selecting_agency, F.data.startswith("select_owner_lic_"))
async def interview_agency_selected(callback: CallbackQuery, state: FSMContext, db_path: str):
    license_code = callback.data.replace("select_owner_lic_", "")
    
    # Check if we are viewing or creating
    curr_state = await state.get_state()
    # Since we use the same state for selecting agency in both creation and viewing, 
    # we need a way to distinguish. Let's check the message text or use a flag.
    # A better way is to check the state data or separate states.
    # For now, let's look at the previous action if possible or use state data.
    
    cases = db.get_all_cases(db_path, license_code)
    if not cases:
        await callback.message.edit_text("❌ این موسسه هیچ پرونده‌ای ندارد.")
        await callback.answer()
        return
    
    # Check if we are in "viewing" mode vs "creating" mode
    # We can use state data
    data = await state.get_data()
    action = data.get("action")

    if action == "view":
        text = f"📅 لیست مصاحبه‌های موسسه {license_code}:\n\n"
        found = False
        for c in cases:
            ivs = db.get_interviews(db_path, c['case_id'])
            if ivs:
                found = True
                for iv in ivs:
                    text += f"🔹 {iv['company_name']} ({iv['scheduled_at_iso']})\n"
        if not found:
            await callback.message.edit_text("ℹ️ هیچ مصاحبه‌ای یافت نشد.")
        else:
            await callback.message.edit_text(text, parse_mode="Markdown", disable_web_page_preview=True)
        await state.clear()
    elif action == "delete":
        text = f"🗑 انتخاب پرونده برای حذف مصاحبه (موسسه {license_code}):"
        await state.set_state(InterviewManagement.selecting_case)
        await callback.message.edit_text(text, reply_markup=kb_case_selection(cases, prefix="case_interview_delete_"))
    else:
        await state.set_state(InterviewManagement.selecting_case)
        await callback.message.edit_text("📅 پرونده مورد نظر از این موسسه را انتخاب کنید:", reply_markup=kb_case_selection(cases, prefix="case_interview_"))
    await callback.answer()

@router.callback_query(InterviewManagement.selecting_client, F.data.startswith("select_client_lic_"))
async def interview_client_selected(callback: CallbackQuery, state: FSMContext, db_path: str):
    license_code = callback.data.replace("select_client_lic_", "")
    cases = db.get_all_cases(db_path, license_code)
    if not cases:
        await callback.message.edit_text("❌ هیچ پرونده‌ای برای این کلاینت یافت نشد.")
        return

    # Check if we are viewing or creating
    curr_state = await state.get_state()
    data = await state.get_data()
    action = data.get("action")
    
    if action == "view":
        text = f"📅 لیست مصاحبه‌های کلاینت {license_code}\n\n"
        found = False
        chunks = []
        current_chunk = text
        
        for c in cases:
            ivs = db.get_interviews(db_path, c['case_id'])
            if ivs:
                found = True
                for iv in ivs:
                    dt_str = iv.get('scheduled_at_iso', '-')
                    if dt_str and 'T' in dt_str:
                        try:
                            from datetime import datetime
                            dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
                            dt_str = dt.strftime("%Y/%m/%d | %H:%M")
                        except:
                            pass
                    
                    # Get selected field
                    extracted = json.loads(iv['extracted_json']) if iv.get('extracted_json') else {}
                    selected_field = extracted.get('selected_field', '')
                    
                    if iv.get('status') == 'pending' and not iv.get('company_name'):
                        continue

                    item_text = f"  - 🔹 رشته: {selected_field or 'نامشخص'}\n"
                    item_text += f"  - 🏢 شرکت: {iv.get('company_name') or 'نامشخص'}\n"
                    item_text += f"  - 📂 پرونده: `{c['case_id']}`\n"
                    item_text += f"  - 👤 متقاضی: {c.get('client_name') or 'نامشخص'}\n"
                    item_text += f"  - ⏰ زمان: {dt_str}\n"
                    item_text += f"  - 📍 شهر: {iv.get('city') or '-'}\n"
                    item_text += f"  - 💻 پلتفرم: {iv.get('platform') or '-'}\n"
                    item_text += f"  - 🔗 لینک: {iv.get('meeting_link') or '-'}\n"
                    if iv.get('username') and iv['username'] not in ('None', '-'):
                        item_text += f"  - 👤 یوزرنیم: `{iv['username']}`\n"
                    if iv.get('password') and iv['password'] not in ('None', '-'):
                        item_text += f"  - 🔑 پسورد: `{iv['password']}`\n"
                    item_text += "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                    
                    if len(current_chunk) + len(item_text) > 3800:
                        chunks.append(current_chunk)
                        current_chunk = item_text
                    else:
                        current_chunk += item_text
        
        if not found:
            await callback.message.edit_text("ℹ️ هیچ مصاحبه‌ای یافت نشد.")
        else:
            if current_chunk:
                chunks.append(current_chunk)
            
            for i, chunk in enumerate(chunks):
                if i == 0:
                    await callback.message.edit_text(chunk, parse_mode="Markdown", disable_web_page_preview=True)
                else:
                    await callback.message.answer(chunk, parse_mode="Markdown", disable_web_page_preview=True)
        await state.clear()
    elif action == "delete":
        text = f"🗑 انتخاب پرونده برای حذف مصاحبه (کلاینت {license_code}):"
        await state.set_state(InterviewManagement.selecting_case)
        await callback.message.edit_text(text, reply_markup=kb_case_selection(cases, prefix="case_interview_delete_"))
    else:
        await state.set_state(InterviewManagement.selecting_case)
        await callback.message.edit_text("📅 پرونده مورد نظر این کلاینت را انتخاب کنید:", reply_markup=kb_case_selection(cases, prefix="case_interview_"))
    await callback.answer()


@router.callback_query(InterviewManagement.selecting_case, F.data.startswith("case_interview_"))
async def interview_case_selected_cb(callback: CallbackQuery, state: FSMContext, db_path: str):
    if callback.data.startswith("case_interview_delete_"):
        case_id = callback.data.replace("case_interview_delete_", "")
        data = await state.get_data()
        await state.update_data(delete_case_id=case_id)
        
        interviews = db.get_interviews(db_path, case_id)
        if not interviews:
            await callback.answer("❌ هیچ مصاحبه‌ای برای این پرونده یافت نشد.", show_alert=True)
            return
            
        text = f"🗑 لیست مصاحبه‌های پرونده {case_id}\nیکی را برای حذف انتخاب کنید:"
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
        buttons = []
        for iv in interviews:
            label = f"{iv['company_name']} | {iv['scheduled_at_iso'] or '-'}"
            buttons.append([InlineKeyboardButton(text=label, callback_data=f"delete_interview_target_{iv['id']}")])
        
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        return

    case_id = callback.data.replace("case_interview_", "")
    case = db.get_case(db_path, case_id)
    if not case:
        await callback.answer("❌ پرونده یافت نشد.")
        return
    await state.update_data(interview_case_id=case_id)
    await state.set_state(InterviewManagement.entering_email_text)
    await callback.message.edit_text(f"📅 ثبت مصاحبه برای پرونده {case_id}\n\nلطفاً متن ایمیل یا جزئیات مصاحبه را وارد کنید:")
    await callback.answer()


def format_interviews_list(interviews: list, title: str, db_path: str) -> str:
    if not interviews:
        return f"📅 {title}\n\nهیچ مصاحبه‌ای یافت نشد."

    text = f"📅 {title}\n"
    text += "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n\n"
    
    # Sort by date
    interviews.sort(key=lambda x: x.get('scheduled_at_iso') or '', reverse=True)
    
    for i, iv in enumerate(interviews[:20], 1):
        # Format date
        display_date = iv.get('scheduled_at_iso', '-')
        if display_date and 'T' in display_date:
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(display_date.replace('Z', '+00:00'))
                display_date = dt.strftime("%Y-%m-%d | %H:%M")
            except:
                pass
        
        status_icon = "⏳"
        status_text = "در انتظار"
        if iv['status'] == 'confirmed': 
            status_icon = "✅"
            status_text = "تایید شده"
        elif iv['status'] == 'cancelled': 
            status_icon = "❌"
            status_text = "لغو شده"
        elif iv['status'] == 'completed': 
            status_icon = "🏁"
            status_text = "انجام شده"
        elif iv['status'] == 'in_progress':
            status_icon = "🔄"
            status_text = "در حال انجام"
        
        case_info = ""
        if iv.get('case_id'):
            case = db.get_case(db_path, iv['case_id'])
            if case:
                case_info = f"👤 کلاینت: {case['client_name']} ({iv['case_id']})\n"

        # Get selected field
        extracted = json.loads(iv['extracted_json']) if iv.get('extracted_json') else {}
        selected_field = extracted.get('selected_field', '')

        text += f"{i}. {status_icon} مصاحبه جدید\n"
        text += f"  - 🔹 رشته: {selected_field or 'نامشخص'}\n"
        text += f"  - 🏢 شرکت: {iv.get('company_name') or 'نام شرکت نامشخص'}\n"
        text += f"  - {case_info}" if case_info else ""
        text += f"  - 👤 کارفرما: {iv.get('employer_name') or '-'}\n"
        text += f"  - 📅 زمان: `{display_date}`\n"
        text += f"  - 🌐 پلتفرم: {iv.get('platform') or '-'}\n"
        text += f"  - 📍 وضعیت: {status_text}\n"
        
        if iv.get('meeting_link'):
            text += f"  - 🔗 [ورود به جلسه]({iv['meeting_link']})\n"
        
        if iv.get('username') and iv['username'] not in ('None', '-'):
            text += f"  - 🔑 ID: `{iv['username']}` "
        if iv.get('password') and iv['password'] not in ('None', '-'):
            text += f"  - 🔒 Pass: `{iv['password']}`"
        
        if iv.get('username') or iv.get('password'):
            text += "\n"
        
        text += "\n\n⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n\n"
    
    return text

@router.message(F.text == "📅 مصاحبه‌ها")
async def view_interviews(message: Message, db_path: str):
    user = db.get_user(db_path, message.from_user.id)
    if not user:
        return

    if user["role"] in ("super_admin", "admin"):
        # Admin view: show all or filter? For now show latest 10
        interviews = db.get_interviews(db_path)
    else:
        # Agency or Direct Client
        license_code = user.get("license_code")
        if not license_code:
            await message.answer("❌ شما لایسنس فعالی ندارید.")
            return
        
        cases = db.get_all_cases(db_path, license_code)
        case_ids = [c["case_id"] for c in cases]
        interviews = []
        for cid in case_ids:
            interviews.extend(db.get_interviews(db_path, cid))
        
        # Sort by date
        interviews.sort(key=lambda x: x.get('scheduled_at_iso') or '', reverse=True)

    if not interviews:
        await message.answer("ℹ️ هیچ مصاحبه‌ای در سیستم ثبت نشده است.")
        return

    text = "📅 لیست مصاحبه‌های شما\n"
    text += "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n\n"

    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    buttons = []
    shown = interviews[:10]

    for i, iv in enumerate(shown, 1):
        # Format date
        display_date = iv.get('scheduled_at_iso', '-')
        if display_date and 'T' in display_date:
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(display_date.replace('Z', '+00:00'))
                display_date = dt.strftime("%Y-%m-%d | %H:%M")
            except:
                pass
        
        status_icon = "⏳"
        if iv['status'] == 'confirmed': status_icon = "✅"
        elif iv['status'] == 'cancelled': status_icon = "❌"
        elif iv['status'] == 'completed': status_icon = "🏁"
        
        # Get selected field
        extracted = json.loads(iv['extracted_json']) if iv.get('extracted_json') else {}
        selected_field = extracted.get('selected_field', '')
        field_suffix = f" ({selected_field})" if selected_field else ""

        text += f"{i}. {status_icon} {iv.get('company_name') or 'نامشخص'}{field_suffix}\n"
        text += f"👤 کارفرما: {iv.get('employer_name') or '-'}\n"
        text += f"📅 زمان: `{display_date}`\n"
        text += f"🌐 پلتفرم: {iv.get('platform') or '-'}\n"
        
        if iv.get('meeting_link'):
            text += f"🔗 [ورود به جلسه]({iv['meeting_link']})\n"
        
        if iv.get('username'):
            text += f"🔑 ID: `{iv['username']}` "
        if iv.get('password'):
            text += f"🔒 Pass: `{iv['password']}`"
        
        text += "\n\n⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n\n"

        # Buttons (delete + apology delete for super admin)
        is_super_admin = (user.get('role') == 'super_admin')
        if user.get('role') in ('super_admin', 'admin'):
            buttons.append([InlineKeyboardButton(text=f"🗑 حذف مصاحبه #{iv['id']}", callback_data=f"delete_interview_{iv['id']}")])
            if is_super_admin:
                buttons.append([InlineKeyboardButton(text=f"🙏 عذرخواهی می‌کنم (حذف با دلیل) #{iv['id']}", callback_data=f"delete_interview_apology_{iv['id']}")])
        else:
            # Regular users can delete only their own interviews (permission check happens in handler)
            buttons.append([InlineKeyboardButton(text=f"🗑 حذف مصاحبه #{iv['id']}", callback_data=f"delete_interview_{iv['id']}")])

    markup = InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None
    await message.answer(text, parse_mode="Markdown", disable_web_page_preview=True, reply_markup=markup)


@router.message(F.text == "💬 پیام‌ها")
async def view_messages(message: Message, db_path: str):
    msgs = db.get_messages_for_user(db_path, message.from_user.id)
    if not msgs:
        await message.answer("ℹ️ شما هیچ پیام دریافتی ندارید.")
        return
        
    text = "💬 پیام‌های دریافتی شما\n"
    text += "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n\n"
    
    for i, m in enumerate(msgs[:10], 1):
        # Format date
        display_date = m.get('created_at', '-')
        if display_date and 'T' in display_date:
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(display_date)
                display_date = dt.strftime("%Y-%m-%d | %H:%M")
            except:
                pass
        
        sender_label = "👤 مدیریت"
        if m['sender_role'] == 'super_admin': sender_label = "⭐ مدیریت کل"
        elif m['sender_role'] == 'admin': sender_label = "👤 ادمین"
        
        text += f"{i}. {sender_label}\n"
        text += f"📅 زمان: `{display_date}`\n"
        text += f"✉️ متن پیام:\n{m['text'] or '_(فایل)_'}\n"
        
        text += "\n⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n\n"
    
    await message.answer(text, parse_mode="Markdown")


@router.message(F.text == "📁 پرونده‌های موسسه")
async def agency_cases(message: Message, db_path: str):
    user = db.get_user(db_path, message.from_user.id)
    if not user or not user.get("license_code"):
        await message.answer("❌ خطا در دسترسی به لایسنس.")
        return
        
    cases = db.get_all_cases(db_path, user["license_code"])
    if not cases:
        await message.answer("ℹ️ هیچ پرونده‌ای برای موسسه شما ثبت نشده است.")
        return
        
    text = "📁 لیست پرونده‌های موسسه شما\n"
    text += "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n\n"
    
    buttons = []
    for c in cases[:10]:
        status_display = get_status_display(c['status'])
        text += f"📋 {c['client_name']}\n"
        text += f"🆔 کد پرونده: `{c['case_id']}`\n"
        text += f"🎓 رشته: {c['field_of_study']}\n"
        text += f"📍 وضعیت: {status_display.replace('آرشیو', 'پایان یافته')}\n"
        text += "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n\n"
        
        buttons.append([InlineKeyboardButton(text=f"🔍 جزئیات {c['client_name']}", callback_data=f"case_view_{c['case_id']}")])
    
    await message.answer(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


@router.message(F.text == "📋 پرونده من")
async def client_case(message: Message, db_path: str):
    user = db.get_user(db_path, message.from_user.id)
    if not user or not user.get("license_code"):
        await message.answer("❌ خطا در دسترسی به لایسنس.")
        return
        
    cases = db.get_all_cases(db_path, user["license_code"])
    if not cases:
        await message.answer("ℹ️ پرونده‌ای برای شما یافت نشد.")
        return
        
    case = cases[0]
    case_id = case["case_id"]
    status_display = get_status_display(case['status'], case.get('yellow_reason'))
    
    interviews = db.get_interviews(db_path, case_id)
    iv_count = len(interviews)
    
    installments = db.get_installments(db_path, case_id)
    inst_text = ""
    if installments:
        parts = []
        for i in installments:
            amount_str = format_amount(i['amount'])
            status_tag = ""
            if i.get('is_paid'):
                status_tag = " (پرداخت شد ✔)"
            
            idx_word = {1: "اول", 2: "دوم", 3: "سوم", 4: "چهارم", 5: "پنجم", 6: "ششم"}.get(i['idx'], f"{i['idx']}")
            parts.append(f"قسط {idx_word}: {amount_str}{status_tag}")
        
        inst_text = "💰 مبالغ اقساط: " + " | ".join(parts)
    
    text = f"📋 جزئیات پرونده شما\n"
    text += "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n\n"
    text += f"👤 نام: {case['client_name']}\n"
    text += f"🆔 کد پرونده: `{case['case_id']}`\n"
    text += f"🎓 رشته: {case['field_of_study']}\n"
    text += f"📍 وضعیت: {status_display.replace('آرشیو', 'پایان یافته')}\n"
    text += f"💰 مبلغ کل: {format_amount(case['total_amount'])}\n"
    text += f"💳 تعداد اقساط: {case['installments_count']}\n"
    text += f"{inst_text}\n"
    text += f"📅 تعداد مصاحبه‌ها: {iv_count}\n"
    text += f"📨 درخواست‌ها: {case.get('in_requests_count', 0)}\n"
    text += f"🎯 جلسات حضوری: {case.get('presentations_count', 0)}\n"
    
    if case.get('payment_notes'):
        text += f"📝 توضیحات پرداخت: {case['payment_notes']}\n"
        
    text += "\n⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
    
    is_admin = user["role"] in ("admin", "super_admin") if user else False
    is_active = bool(case.get("is_active", True))
    await message.answer(text, parse_mode="Markdown", reply_markup=kb_case_detail(case_id, is_admin=is_admin, is_active=is_active))


@router.callback_query(F.data.startswith("case_inst_"))
async def handle_case_installments_callback(callback: CallbackQuery, db_path: str):
    await callback.answer()
    case_id = callback.data.replace("case_inst_", "")
    installments = db.get_installments(db_path, case_id)
    from .keyboards import kb_installment_management
    await callback.message.edit_text(
        f"💰 مدیریت اقساط پرونده {case_id}\n\nبرای تغییر وضعیت پرداخت هر قسط روی آن کلیک کنید:",
        reply_markup=kb_installment_management(case_id, installments)
    )

@router.callback_query(F.data.startswith("inst_toggle_"))
async def handle_installment_toggle_callback(callback: CallbackQuery, db_path: str):
    parts = callback.data.replace("inst_toggle_", "").split("_")
    inst_id = int(parts[0])
    case_id = parts[1]
    
    # Get current status to toggle
    installments = db.get_installments(db_path, case_id)
    inst = next((i for i in installments if i['id'] == inst_id), None)
    if inst:
        new_status = 0 if inst['is_paid'] else 1
        db.update_installment_payment(db_path, inst_id, new_status)
        
        # New logic: If marked as paid, check if we should complete any pending reminders
        if new_status == 1:
            with db.connect(db_path) as conn:
                conn.execute("UPDATE pending_reminders SET is_completed = 1 WHERE installment_id = ?", (inst_id,))
        
        # Task 8: Send notification to the case owner
        if new_status == 1:
            # Re-fetch installments to get updated is_paid status for UI
            installments = db.get_installments(db_path, case_id)
            
            case = db.get_case(db_path, case_id)
            if case:
                idx_word = {1: "اول", 2: "دوم", 3: "سوم", 4: "چهارم", 5: "پنجم", 6: "ششم"}.get(inst['idx'], f"{inst['idx']}")
                amount_str = f"{inst['amount']:,.0f}€"
                
                # Find the user(s) to notify
                owner_license = case['owner_license_code']
                owner_users = db.get_users_by_license(db_path, owner_license)
                
                notif_text = (
                    f"✨ ثبت پرداخت قسط\n\n"
                    f"💼 پرونده: `{case_id}`\n"
                    f"👤 کلاینت: {case['client_name']}\n"
                    f"💰 قسط {idx_word} به مبلغ {amount_str} تایید و در سیستم ثبت شد.\n\n"
                    f"🌸 با تشکر از همراهی شما"
                )
                
                from aiogram.exceptions import TelegramForbiddenError
                for u in owner_users:
                    try:
                        await callback.bot.send_message(u['user_id'], notif_text, parse_mode="Markdown")
                    except TelegramForbiddenError:
                        pass
                    except Exception as e:
                        print(f"[ERROR] Failed to send payment notification: {e}")
        
    # Refresh the menu
    updated_installments = db.get_installments(db_path, case_id)
    from .keyboards import kb_installment_management
    try:
        await callback.message.edit_reply_markup(reply_markup=kb_installment_management(case_id, updated_installments))
    except Exception as e:
        if "message is not modified" not in str(e):
            raise e
    await callback.answer("✅ وضعیت قسط تغییر کرد.")

@router.callback_query(F.data.startswith("iv_follow_"))
async def handle_interview_followup(callback: CallbackQuery, state: FSMContext, bot: Bot, cfg, db_path: str):
    data = callback.data
    await callback.answer()
    parts = data.replace("iv_follow_", "").split("_")
    interview_id = int(parts[0])
    result = parts[1]
    interview = next((i for i in db.get_interviews(db_path) if i["id"] == interview_id), None)
    if not interview:
        await callback.message.answer("خطا! مصاحبه یافت نشد.")
        return
    elif result == "in_progress":
        db.update_interview_followup(db_path, interview_id, "in_progress")
        await callback.message.answer("🙏 مرسی که گفتی! موفق باشی! 💪")
        
        # Task 10: Log to interview history
        interview = db.get_interview(db_path, interview_id)
        if interview:
            case_id = interview['case_id']
            # We can't easily 'add' to history if it's just a status, 
            # but we can ensure the status is updated and maybe add a note.
            db.update_interview_followup(db_path, interview_id, "in_progress", "کاربر وضعیت 'در حال انجام' را انتخاب کرد.")

    elif result == "completed":
        await callback.message.answer("📝 لطفاً توضیحات کوتاهی بده:")
        await state.update_data(interview_id=interview_id, followup_action="completed")
        await state.set_state(InterviewManagement.entering_followup_notes)
    elif result == "no_show":
        await callback.message.answer("📝 لطفاً دلیلشو بنویس:")
        await state.update_data(interview_id=interview_id, followup_action="no_show")
        await state.set_state(InterviewManagement.entering_followup_notes)




@router.message(F.text == "📈 افزایش ظرفیت")
async def increase_capacity_start(message: Message, state: FSMContext, db_path: str):
    licenses = db.get_all_licenses(db_path)
    if not licenses:
        await message.answer("هیچ لایسنسی وجود ندارد.")
        return
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    buttons = []
    for lic in licenses:
        name = lic['agency_name'] or 'کلاینت'
        btn_text = f"{lic['code']} ({name}) - ظرفیت: {lic['used_count']}/{lic['capacity']}"
        buttons.append([InlineKeyboardButton(text=btn_text, callback_data=f"lic_cap_{lic['code']}")])
    await message.answer("لایسنس را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


@router.message(LicenseManagement.selecting_license)
async def select_license_for_capacity(message: Message, state: FSMContext, db_path: str):
    code = message.text.strip().upper()
    lic = db.get_license(db_path, code)
    if not lic:
        await message.answer("لایسنس یافت نشد.")
        return
    await state.update_data(selected_license=code)
    await state.set_state(LicenseManagement.entering_new_capacity)
    await message.answer("ظرفیت جدید را وارد کنید:")


@router.message(LicenseManagement.entering_new_capacity)
async def enter_new_capacity(message: Message, state: FSMContext, db_path: str):
    try:
        new_cap = int(message.text.strip())
        data = await state.get_data()
        code = data.get("selected_license")
        if code:
            db.update_license_capacity(db_path, code, new_cap)
            await message.answer(f"✅ ظرفیت لایسنس {code} به {new_cap} تغییر کرد.", reply_markup=get_smart_kb(kb_licenses_menu, message.from_user.id, db_path))
            await state.clear()
    except ValueError:
        await message.answer("❌ لطفا یک عدد معتبر برای ظرفیت وارد کنید.")

@router.message(F.text == "🔄 غیرفعال/فعال کردن")
async def toggle_license_start(message: Message, state: FSMContext, db_path: str):
    licenses = db.get_all_licenses(db_path)
    if not licenses:
        await message.answer("هیچ لایسنسی وجود ندارد.")
        return
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    buttons = []
    for lic in licenses:
        status = "✅ فعال" if lic["is_active"] else "❌ غیرفعال"
        name = lic['agency_name'] or 'کلاینت'
        btn_text = f"{lic['code']} - {name} ({status})"
        buttons.append([InlineKeyboardButton(text=btn_text, callback_data=f"lic_toggle_{lic['code']}")])
    await message.answer("لایسنس را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


@router.callback_query(F.data.startswith("lic_toggle_"))
async def toggle_license_callback(callback: CallbackQuery, state: FSMContext, db_path: str):
    await callback.answer()
    code = callback.data.replace("lic_toggle_", "")
    lic = db.get_license(db_path, code)
    if not lic:
        await callback.message.answer("لایسنس یافت نشد.")
        return
    db.toggle_license_active(db_path, code)
    new_status = "فعال شد" if not lic.is_active else "غیرفعال شد"
    await callback.message.answer(f"✅ لایسنس {code} {new_status}.", reply_markup=get_smart_kb(kb_licenses_menu, callback.from_user.id, db_path))
    await state.clear()


@router.message(F.text == "👥 مشاهده اعضا")
async def view_members_start(message: Message, state: FSMContext, db_path: str):
    licenses = db.get_all_licenses(db_path)
    if not licenses:
        await message.answer("هیچ لایسنسی وجود ندارد.")
        return
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    buttons = []
    for lic in licenses:
        name = lic['agency_name'] or 'کلاینت'
        buttons.append([InlineKeyboardButton(text=f"{lic['code']} ({name})", callback_data=f"lic_members_{lic['code']}")])
    await message.answer("لایسنس را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


@router.message(LicenseManagement.selecting_license)
async def view_members(message: Message, state: FSMContext, db_path: str):
    code = message.text.strip().upper()
    members = db.get_license_members(db_path, code)
    if not members:
        await message.answer("هیچ عضوی ندارد.")
        return
    text = f"👥 اعضای لایسنس {code}:\n\n"
    for m in members:
        phone = m.get("phone", "ندارد")
        verified = "✅" if m.get("is_phone_verified") else "❌"
        text += f"آیدی: {m['user_id']}\nنام: {m['full_name'] or '-'}\nشماره: {phone} {verified}\nنقش: {m['role']}\n\n"
    await message.answer(text, reply_markup=kb_licenses_menu())
    await state.clear()


@router.message(F.text == "🚫اخراج کاربر")
async def kick_user_start(message: Message, state: FSMContext, db_path: str):
    licenses = db.get_all_licenses(db_path)
    if not licenses:
        await message.answer("هیچ لایسنسی وجود ندارد.")
        return
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    buttons = []
    for lic in licenses:
        name = lic['agency_name'] or 'کلاینت'
        buttons.append([InlineKeyboardButton(text=f"{lic['code']} ({name})", callback_data=f"lic_kick_{lic['code']}")])
    await message.answer("لایسنس را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


@router.callback_query(F.data.startswith("lic_kick_"))
async def kick_user_callback(callback: CallbackQuery, state: FSMContext, db_path: str):
    await callback.answer()
    code = callback.data.replace("lic_kick_", "")
    members = db.get_license_members(db_path, code)
    if not members:
        await callback.message.answer("هیچ عضوی ندارد.")
        return
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    buttons = []
    for m in members:
        name = m['full_name'] or f"آیدی: {m['user_id']}"
        buttons.append([InlineKeyboardButton(text=f"❌ حذف {name}", callback_data=f"kick_user_{m['user_id']}_{code}")])
    await callback.message.answer(f"👥 اعضای لایسنس {code}:\nکاربری که می‌خواهید حذف کنید را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


@router.callback_query(F.data.startswith("kick_user_"))
async def confirm_kick_user(callback: CallbackQuery, db_path: str):
    await callback.answer()
    parts = callback.data.replace("kick_user_", "").split("_")
    user_id = int(parts[0])
    code = parts[1]
    db.kick_user_from_license(db_path, user_id)
    await callback.message.answer(f"✅ کاربر {user_id} از لایسنس {code} حذف شد.", reply_markup=kb_licenses_menu())


@router.message(LicenseManagement.selecting_license)
async def select_license_for_kick(message: Message, state: FSMContext, db_path: str):
    code = message.text.strip().upper()
    members = db.get_license_members(db_path, code)
    if not members:
        await message.answer("هیچ عضوی ندارد.")
        await state.clear()
        return
    await state.update_data(kick_license=code)
    text = "کاربر را انتخاب کنید (آیدی را وارد کنید):\n\n"
    for m in members:
        text += f"- {m['user_id']} | {m['full_name'] or '-'} | {m['role']}\n"
    await message.answer(text, reply_markup=kb_back_main())


@router.message(LicenseManagement.selecting_user_to_kick)
async def kick_user(message: Message, state: FSMContext, db_path: str):
    try:
        user_id = int(message.text.strip())
        data = await state.get_data()
        code = data.get("kick_license")
        db.kick_user_from_license(db_path, user_id)
        await message.answer(f"✅ کاربر {user_id} از لایسنس {code} حذف شد.", reply_markup=kb_licenses_menu())
        await state.clear()
    except ValueError:
        await message.answer("لطفاً آیدی عددی را وارد کنید:")


@router.message(F.text == "🗑 حذف لایسنس")
async def delete_license_start(message: Message, state: FSMContext, db_path: str):
    licenses = db.get_all_licenses(db_path)
    if not licenses:
        await message.answer("هیچ لایسنسی وجود ندارد.")
        return
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    buttons = []
    for lic in licenses:
        name = lic['agency_name'] or 'کلاینت'
        buttons.append([InlineKeyboardButton(text=f"حذف {lic['code']} ({name})", callback_data=f"lic_del_{lic['code']}")])
    await message.answer("لایسنس را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


@router.message(LicenseManagement.selecting_license)
async def delete_license(message: Message, state: FSMContext, db_path: str):
    code = message.text.strip().upper()
    lic = db.get_license(db_path, code)
    if not lic:
        await message.answer("لایسنس یافت نشد.")
        return
    await message.answer(f"آیا لایسنس {code} حذف شود؟", reply_markup=kb_yes_no(f"lic_del_{code}"))


@router.callback_query(F.data.startswith("lic_del_"))
async def delete_license_callback(callback: CallbackQuery, db_path: str):
    print(f"[LOG] lic_del_ called with data: {callback.data}")
    code = callback.data.replace("lic_del_", "")
    await callback.message.answer(f"آیا لایسنس {code} حذف شود؟", reply_markup=kb_yes_no(f"lic_del_{code}"))
    await callback.answer()


@router.callback_query(F.data.startswith("confirm_lic_del_"))
async def confirm_delete_license(callback: CallbackQuery, db_path: str):
    print(f"[LOG] confirm_lic_del_ called with data: {callback.data}")
    await callback.answer()
    if "_no" in callback.data:
        await callback.message.answer("لغو شد.", reply_markup=kb_licenses_menu())
        return
    code = callback.data.replace("confirm_lic_del_", "").replace("_yes", "")
    print(f"[LOG] Deleting license: {code}")
    db.delete_license(db_path, code)
    await callback.message.answer(f"✅ لایسنس {code} حذف شد.", reply_markup=kb_licenses_menu())


@router.callback_query(F.data.startswith("confirm_lic_deact_"))
async def confirm_toggle_license(callback: CallbackQuery, db_path: str):
    print(f"[LOG] confirm_lic_deact_ called with data: {callback.data}")
    await callback.answer()
    if "_no" in callback.data:
        await callback.message.answer("لغو شد.", reply_markup=kb_licenses_menu())
        return
    code = callback.data.replace("confirm_lic_deact_", "").replace("_yes", "")
    print(f"[LOG] Deactivating license: {code}")
    db.update_license(db_path, code, is_active=0)
    await callback.message.answer(f"✅ لایسنس {code} غیرفعال شد.", reply_markup=kb_licenses_menu())


@router.callback_query(F.data.startswith("lic_toggle_"))
async def toggle_license_callback(callback: CallbackQuery, db_path: str):
    print(f"[LOG] lic_toggle_ called with data: {callback.data}")
    await callback.answer()
    code = callback.data.replace("lic_toggle_", "")
    lic = db.get_license(db_path, code)
    if not lic:
        await callback.message.answer("لایسنس یافت نشد.")
        return
    new_status = 0 if lic["is_active"] else 1
    db.update_license(db_path, code, is_active=new_status)
    status_text = "فعال شد" if new_status else "غیرفعال شد"
    await callback.message.answer(f"✅ لایسنس {code} {status_text}.", reply_markup=get_smart_kb(kb_licenses_menu, callback.from_user.id, db_path))


@router.message(F.text == "✏️ ویرایش پرونده")
async def edit_case_start(message: Message, state: FSMContext, db_path: str):
    user = db.get_user(db_path, message.from_user.id)
    if not user: return

    if user["role"] in ("super_admin", "admin"):
        from .keyboards import kb_case_owner_type_inline
        await state.set_state(CaseManagement.editing_selecting_owner_type)
        await message.answer("لطفاً نوع مالک پرونده را انتخاب کنید:", reply_markup=kb_case_owner_type_inline("edit"))
        return

    license_code = user.get("license_code")
    page = 1
    limit = 10
    offset = (page - 1) * limit
    
    cases = db.get_all_cases(db_path, license_code, limit=limit, offset=offset)
    total_cases = db.count_all_cases(db_path, license_code)
    total_pages = (total_cases + limit - 1) // limit
    
    if not cases:
        await message.answer("❌ هیچ پرونده‌ای وجود ندارد.")
        return
        
    await message.answer(
        "✏️ پرونده مورد نظر را برای ویرایش انتخاب کنید:", 
        reply_markup=kb_case_selection(cases, prefix="case_edit_", page=page, total_pages=total_pages)
    )


@router.callback_query(CaseManagement.editing_selecting_owner_type, F.data.startswith("edit_type_"))
async def handle_edit_owner_type(callback: CallbackQuery, state: FSMContext, db_path: str):
    owner_type = callback.data.replace("edit_type_", "")
    await state.update_data(edit_owner_type=owner_type)
    
    from .keyboards import kb_agency_selection, kb_client_license_selection
    all_lics = db.get_all_licenses(db_path)
    
    if owner_type == "agency":
        agencies = [l for l in all_lics if l["license_type"] == "agency"]
        await state.set_state(CaseManagement.editing_selecting_agency)
        await callback.message.edit_text("🏢 لیست موسسات را انتخاب کنید:", reply_markup=kb_agency_selection(agencies, "edit_lic"))
    else:
        clients = [l for l in all_lics if l["license_type"] == "direct_client"]
        await state.set_state(CaseManagement.editing_selecting_client)
        await callback.message.edit_text("👤 لیست کلاینت‌های مستقیم را انتخاب کنید:", reply_markup=kb_client_license_selection(clients, "edit_lic"))


@router.callback_query(F.data == "edit_back_to_type")
async def handle_edit_back_to_type(callback: CallbackQuery, state: FSMContext):
    from .keyboards import kb_case_owner_type_inline
    await state.set_state(CaseManagement.editing_selecting_owner_type)
    await callback.message.edit_text("لطفاً نوع مالک پرونده را انتخاب کنید:", reply_markup=kb_case_owner_type_inline("edit"))


@router.callback_query(F.data.startswith("edit_lic_"))
async def handle_edit_license_selected(callback: CallbackQuery, state: FSMContext, db_path: str):
    license_code = callback.data.replace("edit_lic_", "")
    await state.update_data(edit_license_code_filter=license_code)
    
    page = 1
    limit = 10
    offset = (page - 1) * limit
    
    cases = db.get_all_cases(db_path, license_code, limit=limit, offset=offset)
    total_cases = db.count_all_cases(db_path, license_code)
    total_pages = (total_cases + limit - 1) // limit
    
    if not cases:
        await callback.message.edit_text("❌ هیچ پرونده‌ای برای این لایسنس یافت نشد.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 بازگشت", callback_data="edit_back_to_type")]]))
        return
    
    await callback.message.edit_text(
        "✏️ پرونده مورد نظر را برای ویرایش انتخاب کنید:", 
        reply_markup=kb_case_selection(cases, prefix="case_edit_", page=page, total_pages=total_pages)
    )


@router.callback_query(F.data.startswith("case_edit_page_"))
async def handle_edit_cases_pagination(callback: CallbackQuery, state: FSMContext, db_path: str):
    await callback.answer()
    page = int(callback.data.replace("case_edit_page_", ""))
    
    data = await state.get_data()
    license_code = data.get("edit_license_code_filter")
    
    if not license_code:
        user = db.get_user(db_path, callback.from_user.id)
        license_code = user.get("license_code") if user else None
    
    limit = 10
    offset = (page - 1) * limit
    
    cases = db.get_all_cases(db_path, license_code, limit=limit, offset=offset)
    total_cases = db.count_all_cases(db_path, license_code)
    total_pages = (total_cases + limit - 1) // limit
    
    await callback.message.edit_text(
        "✏️ پرونده مورد نظر را برای ویرایش انتخاب کنید:",
        reply_markup=kb_case_selection(cases, prefix="case_edit_", page=page, total_pages=total_pages)
    )


@router.callback_query(F.data.startswith("case_edit_"))
async def handle_case_edit_callback(callback: CallbackQuery, state: FSMContext, db_path: str):
    await callback.answer()
    case_id = callback.data.replace("case_edit_", "")
    case = db.get_case(db_path, case_id)
    if not case:
        await callback.message.edit_text("❌ پرونده یافت نشد.")
        return
    
    await state.update_data(edit_case_id=case_id)
    in_req = case.get("in_requests_count", 0)
    pres = case.get("presentations_count", 0)
    text = f"📋 ویرایش پرونده: {case_id}\n👤 کلاینت: {case['client_name']}\n\nچه موردی را می‌خواهید ویرایش کنید؟"
    
    from aiogram.types import KeyboardButton, ReplyKeyboardMarkup
    buttons = [
        [KeyboardButton(text="نام کلاینت"), KeyboardButton(text="مبلغ کل")],
        [KeyboardButton(text="تعداد اقساط"), KeyboardButton(text="رشته تحصیلی")],
        [KeyboardButton(text="ویرایش درخواست‌ها"), KeyboardButton(text="ویرایش جلسات حضوری")],
        [KeyboardButton(text="🔙 بازگشت به مرحله قبل"), KeyboardButton(text="🏠 منوی اصلی")],
    ]
    await state.set_state(CaseManagement.selecting_case)
    await callback.message.answer(text, reply_markup=ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True))





@router.message(F.text == "🗑 حذف پرونده")
async def delete_case_start(message: Message, state: FSMContext, db_path: str):
    user = db.get_user(db_path, message.from_user.id)
    if not user: return

    if user["role"] in ("super_admin", "admin"):
        from .keyboards import kb_case_owner_type_inline
        await state.set_state(CaseManagement.deleting_selecting_owner_type)
        await message.answer("لطفاً نوع مالک پرونده را انتخاب کنید:", reply_markup=kb_case_owner_type_inline("delete"))
        return

    license_code = user.get("license_code")
    page = 1
    limit = 10
    offset = (page - 1) * limit
    
    cases = db.get_all_cases(db_path, license_code, limit=limit, offset=offset)
    total_cases = db.count_all_cases(db_path, license_code)
    total_pages = (total_cases + limit - 1) // limit
    
    if not cases:
        await message.answer("❌ هیچ پرونده‌ای وجود ندارد.")
        return
        
    await message.answer(
        "🗑 پرونده مورد نظر را برای حذف انتخاب کنید:", 
        reply_markup=kb_case_selection(cases, prefix="case_delete_", page=page, total_pages=total_pages)
    )


@router.callback_query(CaseManagement.deleting_selecting_owner_type, F.data.startswith("delete_type_"))
async def handle_delete_owner_type(callback: CallbackQuery, state: FSMContext, db_path: str):
    owner_type = callback.data.replace("delete_type_", "")
    await state.update_data(delete_owner_type=owner_type)
    
    from .keyboards import kb_agency_selection, kb_client_license_selection
    all_lics = db.get_all_licenses(db_path)
    
    if owner_type == "agency":
        agencies = [l for l in all_lics if l["license_type"] == "agency"]
        await state.set_state(CaseManagement.deleting_selecting_agency)
        await callback.message.edit_text("🏢 لیست موسسات را انتخاب کنید:", reply_markup=kb_agency_selection(agencies, "delete_lic"))
    else:
        clients = [l for l in all_lics if l["license_type"] == "direct_client"]
        await state.set_state(CaseManagement.deleting_selecting_client)
        await callback.message.edit_text("👤 لیست کلاینت‌های مستقیم را انتخاب کنید:", reply_markup=kb_client_license_selection(clients, "delete_lic"))


@router.callback_query(F.data == "delete_back_to_type")
async def handle_delete_back_to_type(callback: CallbackQuery, state: FSMContext):
    from .keyboards import kb_case_owner_type_inline
    await state.set_state(CaseManagement.deleting_selecting_owner_type)
    await callback.message.edit_text("لطفاً نوع مالک پرونده را انتخاب کنید:", reply_markup=kb_case_owner_type_inline("delete"))


@router.callback_query(F.data.startswith("delete_lic_"))
async def handle_delete_license_selected(callback: CallbackQuery, state: FSMContext, db_path: str):
    license_code = callback.data.replace("delete_lic_", "")
    await state.update_data(delete_license_code_filter=license_code)
    
    page = 1
    limit = 10
    offset = (page - 1) * limit
    
    cases = db.get_all_cases(db_path, license_code, limit=limit, offset=offset)
    total_cases = db.count_all_cases(db_path, license_code)
    total_pages = (total_cases + limit - 1) // limit
    
    if not cases:
        await callback.message.edit_text("❌ هیچ پرونده‌ای برای این لایسنس یافت نشد.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 بازگشت", callback_data="delete_back_to_type")]]))
        return
    
    await callback.message.edit_text(
        "🗑 پرونده مورد نظر را برای حذف انتخاب کنید:", 
        reply_markup=kb_case_selection(cases, prefix="case_delete_", page=page, total_pages=total_pages)
    )


@router.callback_query(F.data.startswith("case_delete_page_"))
async def handle_delete_cases_pagination(callback: CallbackQuery, state: FSMContext, db_path: str):
    await callback.answer()
    page = int(callback.data.replace("case_delete_page_", ""))
    
    data = await state.get_data()
    license_code = data.get("delete_license_code_filter")
    
    if not license_code:
        user = db.get_user(db_path, callback.from_user.id)
        license_code = user.get("license_code") if user else None
    
    limit = 10
    offset = (page - 1) * limit
    
    cases = db.get_all_cases(db_path, license_code, limit=limit, offset=offset)
    total_cases = db.count_all_cases(db_path, license_code)
    total_pages = (total_cases + limit - 1) // limit
    
    await callback.message.edit_text(
        "🗑 پرونده مورد نظر را برای حذف انتخاب کنید:",
        reply_markup=kb_case_selection(cases, prefix="case_delete_", page=page, total_pages=total_pages)
    )


@router.callback_query(F.data.startswith("case_delete_"))
async def handle_case_delete_callback(callback: CallbackQuery, db_path: str):
    await callback.answer()
    case_id = callback.data.replace("case_delete_", "")
    await callback.message.edit_text(f"⚠️ آیا از حذف پرونده {case_id} اطمینان دارید؟", reply_markup=kb_yes_no(f"case_del_{case_id}"))





@router.callback_query(F.data.startswith("confirm_case_del_"))
async def confirm_delete_case(callback: CallbackQuery, db_path: str):
    print(f"[LOG] confirm_case_del_ called with data: {callback.data}")
    await callback.answer()
    case_id = callback.data.replace("confirm_case_del_", "").replace("_yes", "")
    if "_no" in callback.data:
        await callback.message.answer("لغو شد.", reply_markup=get_smart_kb(kb_cases_menu, callback.from_user.id, db_path))
        return
    print(f"[LOG] Deleting case: {case_id}")
    db.delete_case(db_path, case_id)
    await callback.message.answer(f"✅ پرونده {case_id} حذف شد.", reply_markup=get_smart_kb(kb_cases_menu, callback.from_user.id, db_path))


@router.message(CaseManagement.selecting_case, F.text.in_(["نام کلاینت", "مبلغ کل", "تعداد اقساط", "رشته تحصیلی"]))
async def start_case_field_edit(message: Message, state: FSMContext):
    field = message.text
    field_map = {
        "نام کلاینت": ("client_name", "نام جدید کلاینت را وارد کنید:"),
        "مبلغ کل": ("total_amount", "مبلغ کل جدید را به یورو وارد کنید:"),
        "تعداد اقساط": ("installments_count", "تعداد اقساط جدید را وارد کنید:"),
        "رشته تحصیلی": ("field_of_study", "رشته تحصیلی جدید را وارد کنید:"),
    }
    key, prompt = field_map[field]
    await state.update_data(edit_field=key, edit_field_display=field)
    await state.set_state(CaseManagement.waiting_for_edit_value)
    await message.answer(prompt, reply_markup=kb_back_main())


@router.message(CaseManagement.waiting_for_edit_value, F.text == "🔙 بازگشت به مرحله قبل")
async def back_to_edit_menu(message: Message, state: FSMContext, db_path: str):
    data = await state.get_data()
    case_id = data.get("edit_case_id")
    case = db.get_case(db_path, case_id)
    if not case:
        await message.answer("❌ پرونده یافت نشد.")
        return
    
    text = f"📋 ویرایش پرونده: {case_id}\n👤 کلاینت: {case['client_name']}\n\nچه موردی را می‌خواهید ویرایش کنید؟"
    from aiogram.types import KeyboardButton, ReplyKeyboardMarkup
    buttons = [
        [KeyboardButton(text="نام کلاینت"), KeyboardButton(text="مبلغ کل")],
        [KeyboardButton(text="تعداد اقساط"), KeyboardButton(text="رشته تحصیلی")],
        [KeyboardButton(text="ویرایش درخواست‌ها"), KeyboardButton(text="ویرایش جلسات حضوری")],
        [KeyboardButton(text="🔙 بازگشت به مرحله قبل"), KeyboardButton(text="🏠 منوی اصلی")],
    ]
    await state.set_state(CaseManagement.selecting_case)
    await message.answer(text, reply_markup=ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True))





@router.message(CaseManagement.selecting_case, F.text == "ویرایش درخواست‌ها")
async def edit_in_requests_start(message: Message, state: FSMContext, db_path: str):
    data = await state.get_data()
    case_id = data.get("edit_case_id")
    if not case_id:
        await message.answer("لطفاً ابتدا پرونده را انتخاب کنید.")
        return
    
    fields = db.get_case_fields(db_path, case_id)
    if not fields:
        await state.update_data(editing_counter="in_requests")
        await state.set_state(CaseManagement.editing_counter)
        case = db.get_case(db_path, case_id)
        await message.answer(f"📨 درخواست‌های فعلی: {case.get('in_requests_count', 0)}\nعدد جدید را وارد کنید:", reply_markup=kb_back_main())
    else:
        await state.update_data(editing_counter_type="in_requests")
        await state.set_state(CaseManagement.selecting_field_for_counter)
        await message.answer("🎓 لطفاً رشته مورد نظر برای ویرایش درخواست‌ها را انتخاب کنید:", reply_markup=kb_field_selection(fields, "field_counter_"))

@router.message(CaseManagement.selecting_case, F.text == "ویرایش جلسات حضوری")
async def edit_presentations_start(message: Message, state: FSMContext, db_path: str):
    data = await state.get_data()
    case_id = data.get("edit_case_id")
    if not case_id:
        await message.answer("لطفاً ابتدا پرونده را انتخاب کنید.")
        return

    fields = db.get_case_fields(db_path, case_id)
    if not fields:
        await state.update_data(editing_counter="presentations")
        await state.set_state(CaseManagement.editing_counter)
        case = db.get_case(db_path, case_id)
        await message.answer(f"🎯 جلسات حضوری فعلی: {case.get('presentations_count', 0)}\nعدد جدید را وارد کنید:", reply_markup=kb_back_main())
    else:
        await state.update_data(editing_counter_type="presentations")
        await state.set_state(CaseManagement.selecting_field_for_counter)
        await message.answer("🎓 لطفاً رشته مورد نظر برای ویرایش جلسات حضوری را انتخاب کنید:", reply_markup=kb_field_selection(fields, "field_counter_"))

@router.callback_query(CaseManagement.selecting_field_for_counter, F.data.startswith("field_counter_"))
async def select_field_for_counter(callback: CallbackQuery, state: FSMContext, db_path: str):
    field_id = int(callback.data.replace("field_counter_", ""))
    data = await state.get_data()
    counter_type = data.get("editing_counter_type")
    
    field = db.get_case_field(db_path, field_id)
    if not field:
        await callback.answer("❌ رشته یافت نشد.", show_alert=True)
        return
        
    await state.update_data(editing_field_id=field_id)
    await state.set_state(CaseManagement.editing_counter)
    
    current_val = field['requests_count'] if counter_type == "in_requests" else field['presentations_count']
    label = "درخواست‌ها" if counter_type == "in_requests" else "جلسات حضوری"
    
    await callback.message.answer(f"🎓 رشته: {field['field_name']}\n📊 {label} فعلی: {current_val}\nعدد جدید را وارد کنید:", reply_markup=kb_back_main())
    await callback.answer()

@router.message(CaseManagement.editing_counter, F.text)
async def handle_counter_edit(message: Message, state: FSMContext, bot: Bot, db_path: str):
    if message.text in ("🔙 بازگشت به مرحله قبل", "🏠 منوی اصلی"):
        await state.set_state(CaseManagement.selecting_case)
        return

    try:
        new_val = int(message.text.strip())
        if new_val < 0: raise ValueError
    except ValueError:
        await message.answer("❌ لطفاً یک عدد معتبر وارد کنید:")
        return

    data = await state.get_data()
    counter_type = data.get("editing_counter_type") or data.get("editing_counter")
    field_id = data.get("editing_field_id")
    case_id = data.get("edit_case_id")

    if field_id:
        if counter_type == "in_requests":
            db.update_case_field_counters(db_path, field_id, requests=new_val)
        else:
            db.update_case_field_counters(db_path, field_id, presentations=new_val)
        
        field = db.get_case_field(db_path, field_id)
        label = "درخواست‌ها" if counter_type == "in_requests" else "جلسات حضوری"
        await message.answer(f"✅ {label} رشته «{field['field_name']}» به `{new_val}` تغییر یافت.", reply_markup=kb_cases_menu())
    else:
        # Legacy support
        if counter_type == "in_requests":
            db.update_case_counters(db_path, case_id, in_requests=new_val)
        else:
            db.update_case_counters(db_path, case_id, presentations=new_val)
        await message.answer(f"✅ آمار پرونده به `{new_val}` تغییر یافت.", reply_markup=kb_cases_menu())

    await state.clear()


@router.message(CaseManagement.waiting_for_edit_value, F.text)
async def handle_case_edit_value(message: Message, state: FSMContext, bot: Bot, db_path: str):
    data = await state.get_data()
    case_id = data.get("edit_case_id")
    field = data.get("edit_field")
    field_display = data.get("edit_field_display", field)
    
    if not case_id or not field:
        return

    new_value = message.text.strip()
    
    # Validation
    if field in ("total_amount", "installments_count"):
        try:
            new_value = float(new_value) if field == "total_amount" else int(new_value)
            if new_value < 0: raise ValueError
        except ValueError:
            await message.answer("❌ لطفاً عدد معتبر (مثبت) وارد کنید:")
            return

    # Special handling for installments count
    if field == "installments_count":
        await state.update_data(new_installments_count=new_value, current_installment_idx=1, temp_amounts=[])
        await state.set_state(CaseManagement.waiting_for_installment_edit)
        await message.answer(f"💰 مبلغ قسط شماره ۱ از {new_value} را وارد کنید:")
        return

    # Update DB for other fields
    with db.connect(db_path) as conn:
        conn.execute(f"UPDATE cases SET {field} = ? WHERE case_id = ?", (new_value, case_id))
    
    # Notify Agency/Client
    case = db.get_case(db_path, case_id)
    if case:
        owner_code = case['owner_license_code']
        users = db.get_users_by_license(db_path, owner_code)
        notify_text = f"🔄 پرونده {case_id} ویرایش شد.\n🔹 فیلد {field_display} به `{new_value}` تغییر یافت."
        for u in users:
            try:
                await bot.send_message(u['user_id'], notify_text)
            except: pass

    # Escape Markdown special characters to avoid parse errors
    escaped_value = str(new_value).replace("_", "\\_").replace("*", "\\*").replace("`", "\\`").replace("[", "\\[")
    await message.answer(f"✅ فیلد {field_display} با موفقیت به `{escaped_value}` تغییر یافت.", parse_mode="Markdown", reply_markup=get_smart_kb(kb_cases_menu, message.from_user.id, db_path))
    await state.clear()


@router.message(CaseManagement.waiting_for_installment_edit, F.text)
async def handle_installment_amount_edit(message: Message, state: FSMContext, bot: Bot, db_path: str):
    data = await state.get_data()
    case_id = data.get("edit_case_id")
    count = data.get("new_installments_count")
    idx = data.get("current_installment_idx")
    amounts = data.get("temp_amounts", [])

    try:
        amount = float(message.text.strip())
        if amount < 0: raise ValueError
    except ValueError:
        await message.answer(f"❌ عدد معتبر وارد کنید.\n💰 مبلغ قسط شماره {idx} را وارد کنید:")
        return

    amounts.append(amount)
    
    if idx < count:
        new_idx = idx + 1
        await state.update_data(temp_amounts=amounts, current_installment_idx=new_idx)
        await message.answer(f"💰 مبلغ قسط شماره {new_idx} از {count} را وارد کنید:")
    else:
        # All amounts collected
        with db.connect(db_path) as conn:
            conn.execute("UPDATE cases SET installments_count = ? WHERE case_id = ?", (count, case_id))
            conn.execute("DELETE FROM installments WHERE case_id = ?", (case_id,))
            for i, amt in enumerate(amounts, 1):
                conn.execute("INSERT INTO installments(case_id, idx, amount) VALUES (?, ?, ?)", (case_id, i, amt))
        
        # Notify Agency/Client
        case = db.get_case(db_path, case_id)
        if case:
            owner_code = case['owner_license_code']
            users = db.get_users_by_license(db_path, owner_code)
            notify_text = f"🔄 اقساط پرونده {case_id} ویرایش شد.\n🔹 تعداد اقساط جدید: {count}"
            for u in users:
                try:
                    await bot.send_message(u['user_id'], notify_text)
                except: pass

        await message.answer(f"✅ تعداد اقساط به {count} تغییر یافت و مبالغ بروزرسانی شدند.", reply_markup=get_smart_kb(kb_cases_menu, message.from_user.id, db_path))
        await state.clear()


@router.message(CaseManagement.editing_counter, F.text == "🔙 بازگشت به مرحله قبل")
async def back_from_counter_edit(message: Message, state: FSMContext, db_path: str):
    data = await state.get_data()
    case_id = data.get("edit_case_id")
    case = db.get_case(db_path, case_id)
    if not case:
        await message.answer("❌ پرونده یافت نشد.")
        return
    
    text = f"📋 ویرایش پرونده: {case_id}\n👤 کلاینت: {case['client_name']}\n\nچه موردی را می‌خواهید ویرایش کنید؟"
    from aiogram.types import KeyboardButton, ReplyKeyboardMarkup
    buttons = [
        [KeyboardButton(text="نام کلاینت"), KeyboardButton(text="مبلغ کل")],
        [KeyboardButton(text="تعداد اقساط"), KeyboardButton(text="رشته تحصیلی")],
        [KeyboardButton(text="ویرایش درخواست‌ها"), KeyboardButton(text="ویرایش جلسات حضوری")],
        [KeyboardButton(text="🔙 بازگشت به مرحله قبل"), KeyboardButton(text="🏠 منوی اصلی")],
    ]
    await state.set_state(CaseManagement.selecting_case)
    await message.answer(text, reply_markup=ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True))


@router.message(CaseManagement.editing_counter)
async def handle_counter_edit(message: Message, state: FSMContext, bot: Bot, db_path: str):
    data = await state.get_data()
    case_id = data.get("edit_case_id")
    counter_type = data.get("editing_counter")
    if not case_id or not counter_type:
        return
    try:
        value = int(message.text.strip())
        if value < 0: raise ValueError
        
        if counter_type == "in_requests":
            db.update_case_counters(db_path, case_id, in_requests=value)
            msg = f"✅ شماره درخواست‌ها به {value} تغییر کرد."
        else:
            db.update_case_counters(db_path, case_id, presentations=value)
            msg = f"✅ تعداد جلسات حضوری به {value} تغییر کرد."
            
        # Notify Agency/Client
        case = db.get_case(db_path, case_id)
        if case:
            owner_code = case['owner_license_code']
            users = db.get_users_by_license(db_path, owner_code)
            field_name = "تعداد درخواست‌ها" if counter_type == "in_requests" else "تعداد جلسات حضوری"
            notify_text = f"🔄 پرونده {case_id} ویرایش شد.\n🔹 {field_name} به `{value}` تغییر یافت."
            for u in users:
                try:
                    await bot.send_message(u['user_id'], notify_text)
                except: pass

        await message.answer(msg, reply_markup=get_smart_kb(kb_cases_menu, message.from_user.id, db_path))
        await state.clear()
    except ValueError:
        await message.answer("❌ لطفاً یک عدد معتبر (مثبت) وارد کنید:")


@router.message(CaseManagement.entering_case_comment)
async def handle_case_comment_text(message: Message, state: FSMContext):
    comment_text = message.text.strip() if message.text else message.caption.strip() if message.caption else ""
    file_id = None
    if message.photo:
        file_id = message.photo[-1].file_id
    elif message.document:
        file_id = message.document.file_id
    
    data = await state.get_data()
    case_id = data.get("case_id_for_comment")
    
    await state.update_data(pending_comment=comment_text, pending_file_id=file_id)
    await state.set_state(CaseManagement.confirming_comment_visibility)
    
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    buttons = [
        [InlineKeyboardButton(text="🔒 فقط سوپر ادمین (محرمانه)", callback_data=f"comment_visibility_1_{case_id}")],
        [InlineKeyboardButton(text="📢 اطلاع به موسسه/کلاینت (عمومی)", callback_data=f"comment_visibility_0_{case_id}")],
        [InlineKeyboardButton(text="❌ انصراف", callback_data="back_to_cases_menu")]
    ]
    await message.answer("❓ این کامنت برای چه کسانی نمایش داده شود؟\n(در صورت انتخاب گزینه عمومی، پیام به تلگرام موسسه/کلاینت ارسال می‌شود)", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


@router.message(Command(re.compile(r"edit_comment_(\d+)")))
async def cmd_edit_comment(message: Message, state: FSMContext, db_path: str):
    user = db.get_user(db_path, message.from_user.id)
    if not user or user['role'] != 'super_admin':
        return
        
    match = re.match(r"/edit_comment_(\d+)", message.text)
    if match:
        comment_id = int(match.group(1))
        comment = db.get_case_comment(db_path, comment_id)
        if comment:
            await state.update_data(edit_comment_id=comment_id, case_id=comment['case_id'])
            await state.set_state(CaseManagement.editing_case_comment)
            await message.answer(f"📝 متن جدید برای کامنت پرونده {comment['case_id']} را وارد کنید:\n\nمتن فعلی: `{comment['comment_text']}`")


@router.message(Command(re.compile(r"del_comment_(\d+)")))
async def cmd_del_comment(message: Message, db_path: str):
    user = db.get_user(db_path, message.from_user.id)
    if not user or user['role'] != 'super_admin':
        return
        
    match = re.match(r"/del_comment_(\d+)", message.text)
    if match:
        comment_id = int(match.group(1))
        comment = db.get_case_comment(db_path, comment_id)
        if comment:
            case_id = comment['case_id']
            db.delete_case_comment(db_path, comment_id)
            await message.answer("✅ کامنت با موفقیت حذف شد.")
            
            # Refresh case view
            class FakeCallback:
                def __init__(self, message, user, data):
                    self.message = message
                    self.from_user = user
                    self.data = data
                async def answer(self): pass
            await handle_case_view_callback(FakeCallback(message, message.from_user, f"case_view_{case_id}"), db_path)


@router.message(CaseManagement.editing_case_comment)
async def handle_edit_comment_text(message: Message, state: FSMContext, db_path: str):
    new_text = message.text.strip()
    data = await state.get_data()
    comment_id = data.get("edit_comment_id")
    case_id = data.get("case_id")
    
    db.update_case_comment(db_path, comment_id, new_text)
    await message.answer("✅ کامنت با موفقیت ویرایش شد.")
    await state.clear()
    
    # Refresh case view
    case = db.get_case(db_path, case_id)
    if case:
        class FakeCallback:
            def __init__(self, message, user, data):
                self.message = message
                self.from_user = user
                self.data = data
            async def answer(self): pass
        await handle_case_view_callback(FakeCallback(message, message.from_user, f"case_view_{case_id}"), db_path)


@router.message(CaseManagement.entering_status_reason)
async def handle_status_reason(message: Message, state: FSMContext, db_path: str):
    data = await state.get_data()
    field_id = data.get("status_field_id")
    case_id = data.get("status_case_id")
    new_status = data.get("new_status")
    reason = message.text.strip()
    
    if field_id:
        await process_status_update(message, state, db_path, reason)
    elif case_id and new_status:
        # Legacy support
        db.update_case_status(db_path, case_id, new_status, yellow_reason=reason)
        await message.answer(f"✅ وضعیت پرونده به {new_status} تغییر یافت.")
        await state.clear()
    else:
        await message.answer("❌ خطا در شناسایی اطلاعات. مجدداً تلاش کنید.")
        await state.clear()


@router.message(F.text == "📦 آرشیو پرونده‌ها")
async def archived_cases(message: Message, db_path: str):
    user = db.get_user(db_path, message.from_user.id)
    if user and user.get("license_code"):
        cases = db.get_all_cases(db_path, user["license_code"])
    else:
        cases = db.get_all_cases(db_path)
    archived = [c for c in cases if not c.get("is_active")]
    if not archived:
        await message.answer("هیچ پرونده آرشیو شده‌ای وجود ندارد.")
        return
    text = "📁 پرونده‌های آرشیو:\n\n"
    for c in archived:
        text += f"{c['case_id']} | {c['client_name']}\n"
    await message.answer(text, reply_markup=get_smart_kb(kb_cases_menu, message.from_user.id, db_path))


@router.message(F.text == "🏢 ارسال به موسسه")
async def send_to_agency_start(message: Message, state: FSMContext, db_path: str):
    agencies = db.get_all_agencies(db_path)
    if not agencies:
        await message.answer("هیچ موسسه‌ای وجود ندارد.")
        return
    
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    buttons = []
    for ag in agencies:
        buttons.append([InlineKeyboardButton(
            text=f"🏢 {ag['agency_name']} ({ag['code']})",
            callback_data=f"msg_target_agency_{ag['code']}"
        )])
    
    await state.set_state(MessageManagement.selecting_agency)
    await message.answer("👇 موسسه مورد نظر برای ارسال پیام را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


@router.callback_query(F.data.startswith("msg_target_agency_"))
async def select_agency_for_message(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    code = callback.data.replace("msg_target_agency_", "")
    await state.update_data(target_license=code, msg_type="targeted")
    await state.set_state(MessageManagement.entering_message_text)
    await callback.message.edit_text(f"📝 پیام خود را برای موسسه {code} بنویسید و همینجا ارسال کنید:")


@router.message(MessageManagement.entering_message_text)
async def enter_message_text(message: Message, state: FSMContext, bot: Bot, db_path: str):
    data = await state.get_data()
    text = message.text.strip()
    
    # Check if we are in scheduling mode
    if "sched_target_code" in data:
        await state.update_data(sched_text=text)
        await state.set_state(MessageManagement.entering_schedule_time)
        await message.answer(
            "⏰ مرحله آخر: زمان ارسال\n\n"
            "لطفاً زمان ارسال پیام را با فرمت زیر وارد کنید:\n"
            "`YYYY-MM-DD HH:MM`\n\n"
            "مثال: `2024-03-25 14:30` (به وقت سرور)",
            parse_mode="Markdown"
        )
        return

    msg_type = data.get("msg_type", "broadcast")
    if msg_type == "targeted":
        target_license = data.get("target_license")
        if target_license:
            members = db.get_users_by_license(db_path, target_license)
            sent = 0
            for m in members:
                try:
                    await bot.send_message(m["user_id"], f"💬 پیام از مدیریت:\n\n{text}")
                    sent += 1
                except:
                    pass
            await message.answer(f"✅ پیام به {sent} نفر با موفقیت ارسال شد.", reply_markup=get_smart_kb(kb_send_message_menu, message.from_user.id, db_path))
        else:
            await message.answer("❌ خطایی رخ داد. گیرنده پیام مشخص نیست.", reply_markup=get_smart_kb(kb_send_message_menu, message.from_user.id, db_path))
    else:
        # Broadcast logic: send to all users who are verified and have a role
        all_users = db.get_users_by_role(db_path, "direct_client")
        agency_users = db.get_users_by_role(db_path, "agency")
        all_targets = all_users + agency_users
        
        sent = 0
        for u in all_targets:
            try:
                await bot.send_message(u["user_id"], f"📢 پیام همگانی از مدیریت:\n\n{text}")
                sent += 1
            except:
                pass
        await message.answer(f"✅ پیام همگانی به {sent} کاربر ارسال شد.", reply_markup=get_smart_kb(kb_send_message_menu, message.from_user.id, db_path))
    
    await state.clear()


@router.message(F.text == "👤 ارسال به کلاینت")
async def send_to_client_start(message: Message, state: FSMContext, db_path: str):
    clients = db.get_all_direct_clients(db_path)
    if not clients:
        await message.answer("هیچ کلاینت مستقیمی وجود ندارد.")
        return
    
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    buttons = []
    for c in clients:
        buttons.append([InlineKeyboardButton(
            text=f"👤 {c['agency_name']} ({c['code']})",
            callback_data=f"msg_target_client_{c['code']}"
        )])
    
    await state.set_state(MessageManagement.selecting_client)
    await message.answer("👇 کلاینت مورد نظر را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


@router.callback_query(F.data.startswith("msg_target_client_"))
async def select_client_for_message(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    code = callback.data.replace("msg_target_client_", "")
    await state.update_data(target_license=code, msg_type="targeted")
    await state.set_state(MessageManagement.entering_message_text)
    await callback.message.edit_text(f"📝 پیام خود را برای کلاینت {code} بنویسید:")


@router.message(F.text == "📢 ارسال همگانی")
async def broadcast_start(message: Message, state: FSMContext):
    await state.update_data(msg_type="broadcast")
    await state.set_state(MessageManagement.entering_message_text)
    await message.answer("📣 پیام همگانی خود را بنویسید (این پیام برای همه کلاینت‌های مستقیم ارسال می‌شود):")


@router.message(F.text.in_(["⏰ پیام زمان‌بندی شده", "پیام زمان‌بندی شده ⏰"]))
async def scheduled_message_start(message: Message, state: FSMContext, db_path: str):
    from .keyboards import kb_scheduling_type
    await state.set_state(MessageManagement.selecting_recipient_type)
    await message.answer(
        "⏰ تنظیم پیام زمان‌بندی شده\n\n"
        "ابتدا انتخاب کنید که پیام برای چه کسی ارسال شود:",
        reply_markup=kb_scheduling_type(),
        parse_mode="Markdown"
    )

@router.callback_query(F.data == "cancel_scheduling")
async def cancel_scheduling(callback: CallbackQuery, state: FSMContext, db_path: str):
    await callback.answer("لغو شد")
    await state.clear()
    await callback.message.edit_text("❌ عملیات با موفقیت لغو شد.")

@router.callback_query(F.data.startswith("sched_type_"))
async def select_sched_type(callback: CallbackQuery, state: FSMContext, db_path: str):
    await callback.answer()
    recipient_type = callback.data.replace("sched_type_", "")
    await state.update_data(sched_recipient_type=recipient_type)
    
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    buttons = []
    
    if recipient_type == "agency":
        agencies = db.get_all_agencies(db_path)
        for ag in agencies:
            buttons.append([InlineKeyboardButton(text=f"🏢 {ag['agency_name']}", callback_data=f"sel_sched_target_{ag['code']}")])
        text = "🏢 موسسه مورد نظر را انتخاب کنید:"
    else:
        clients = db.get_all_direct_clients(db_path)
        for c in clients:
            buttons.append([InlineKeyboardButton(text=f"👤 {c['agency_name']}", callback_data=f"sel_sched_target_{c['code']}")])
        text = "👤 کلاینت مورد نظر را انتخاب کنید:"
    
    buttons.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="back_to_sched_type")])
    
    await state.set_state(MessageManagement.selecting_agency if recipient_type == "agency" else MessageManagement.selecting_client)
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@router.callback_query(F.data == "back_to_sched_type")
async def back_to_sched_type(callback: CallbackQuery, state: FSMContext):
    from .keyboards import kb_scheduling_type
    await state.set_state(MessageManagement.selecting_recipient_type)
    await callback.message.edit_text("انتخاب کنید که پیام برای چه کسی ارسال شود:", reply_markup=kb_scheduling_type())

@router.callback_query(F.data.startswith("sel_sched_target_"))
async def select_sched_target(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    target_code = callback.data.replace("sel_sched_target_", "")
    await state.update_data(sched_target_code=target_code)
    await state.set_state(MessageManagement.entering_message_text)
    await callback.message.edit_text(f"📝 لایسنس `{target_code}` انتخاب شد\n\nحالا متن پیام خود را بنویسید:", parse_mode="Markdown")

# Note: The existing entering_message_text handler needs to be aware of scheduling mode.
# I will modify the existing handler or add a specific one.
# Let's add a specific one for scheduling text to avoid breaking the normal send message flow.


@router.message(F.text == "📋 ارسال بر اساس پرونده")
async def send_by_case_start(message: Message, state: FSMContext, db_path: str):
    cases = db.get_all_cases(db_path)
    if not cases:
        await message.answer("هیچ پرونده‌ای وجود ندارد.")
        return
    
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    buttons = []
    for c in cases[:15]: # Show first 15 cases with buttons
        buttons.append([InlineKeyboardButton(
            text=f"📂 {c['case_id']} | {c['client_name']}",
            callback_data=f"msg_target_case_{c['case_id']}"
        )])
    
    await state.set_state(MessageManagement.selecting_case)
    await message.answer("👇 پرونده مورد نظر را برای ارسال پیام به کلاینت آن انتخاب کنید:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


@router.callback_query(F.data.startswith("msg_target_case_"))
async def select_case_for_message(callback: CallbackQuery, state: FSMContext, db_path: str):
    await callback.answer()
    case_id = callback.data.replace("msg_target_case_", "")
    case = db.get_case(db_path, case_id)
    if not case:
        await callback.message.edit_text("❌ پرونده یافت نشد.")
        return
    await state.update_data(target_license=case["owner_license_code"], msg_type="targeted")
    await state.set_state(MessageManagement.entering_message_text)
    await callback.message.edit_text(f"📝 پیام خود را برای کلاینت پرونده {case_id} بنویسید:")


@router.message(F.text == "➕ افزودن ادمین")
async def add_admin_start(message: Message, state: FSMContext):
    await state.set_state(AdminManagement.entering_admin_id)
    await message.answer("آیدی کاربر را وارد کنید:")


@router.message(F.text == "💰 یادآوری اقساط")
async def installment_reminder_start(message: Message, state: FSMContext, db_path: str, cfg):
    print(f"DEBUG: installment_reminder_start triggered by user {message.from_user.id}")
    try:
        # Check if user is super admin or has permission
        user = db.get_user(db_path, message.from_user.id)
        is_super = (message.from_user.id == cfg.super_admin_id) or (user and user.get("role") == "super_admin")
        
        if not is_super:
            await message.answer("❌ این بخش فقط برای سوپر ادمین در دسترس است.")
            return
        
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
        buttons = [
            [InlineKeyboardButton(text="🏢 موسسه", callback_data="remind_type_agency")],
            [InlineKeyboardButton(text="👤 کلاینت بلاگر", callback_data="remind_type_blogger")],
            [InlineKeyboardButton(text="🤝 کلاینت مستقیم", callback_data="remind_type_direct_client")],
            [InlineKeyboardButton(text="❌ انصراف", callback_data="cancel_installment_remind")]
        ]
        await state.set_state(InstallmentReminder.selecting_owner_type)
        await message.answer("👇 نوع مالک پرونده را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    except Exception as e:
        await message.answer(f"❌ خطا: {str(e)}")
        print(f"Error in installment_reminder_start: {e}")

@router.callback_query(InstallmentReminder.selecting_owner_type, F.data.startswith("remind_type_"))
async def select_owner_type_remind(callback: CallbackQuery, state: FSMContext, db_path: str):
    await callback.answer()
    owner_type = callback.data.replace("remind_type_", "")
    await state.update_data(remind_owner_type=owner_type)
    
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    
    licenses = []
    if owner_type == "agency":
        licenses = db.get_all_agencies(db_path)
    elif owner_type == "blogger":
        with db.connect(db_path) as conn:
            rows = conn.execute("SELECT code, agency_name FROM licenses WHERE license_type = 'blogger'").fetchall()
            licenses = [dict(r) for r in rows]
    else:
        licenses = db.get_all_direct_clients(db_path)
        
    if not licenses:
        await callback.message.edit_text("❌ هیچ موردی یافت نشد.", reply_markup=None)
        await state.clear()
        return

    buttons = []
    for lic in licenses:
        name = lic.get('agency_name') or lic['code']
        buttons.append([InlineKeyboardButton(text=str(name), callback_data=f"remind_lic_{lic['code']}")])
    
    buttons.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="back_to_remind_type")])
    await state.set_state(InstallmentReminder.selecting_agency)
    await callback.message.edit_text("👇 انتخاب کنید:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@router.callback_query(InstallmentReminder.selecting_agency, F.data.startswith("remind_lic_"))
async def select_lic_remind(callback: CallbackQuery, state: FSMContext, db_path: str):
    await callback.answer()
    lic_code = callback.data.replace("remind_lic_", "")
    await state.update_data(remind_lic_code=lic_code)
    
    cases = db.get_all_cases(db_path, license_code=lic_code)
    if not cases:
        await callback.message.edit_text("❌ هیچ پرونده‌ای برای این لایسنس یافت نشد.")
        await state.clear()
        return
        
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    buttons = []
    for c in cases:
        buttons.append([InlineKeyboardButton(text=f"📂 {c['client_name']} ({c['case_id']})", callback_data=f"remind_case_{c['case_id']}")])
    
    buttons.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="back_to_remind_lics")])
    await state.set_state(InstallmentReminder.selecting_case)
    await callback.message.edit_text("👇 پرونده مورد نظر را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@router.callback_query(InstallmentReminder.selecting_case, F.data.startswith("remind_case_"))
async def select_case_remind(callback: CallbackQuery, state: FSMContext, db_path: str):
    await callback.answer()
    case_id = callback.data.replace("remind_case_", "")
    await state.update_data(remind_case_id=case_id)
    
    installments = db.get_installments(db_path, case_id)
    if not installments:
        await callback.message.edit_text("❌ هیچ قسطی برای این پرونده تعریف نشده است.")
        await state.clear()
        return
        
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    buttons = []
    for inst in installments:
        status = "✅ پرداخت شده" if inst['is_paid'] else "❌ پرداخت نشده"
        buttons.append([InlineKeyboardButton(text=f"قسط {inst['idx']}: {inst['amount']}€ ({status})", callback_data=f"remind_inst_{inst['id']}")])
    
    buttons.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="back_to_remind_cases")])
    await state.set_state(InstallmentReminder.selecting_installment)
    await callback.message.edit_text("👇 کدام قسط را یادآوری کنم؟", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@router.callback_query(InstallmentReminder.selecting_installment, F.data.startswith("remind_inst_"))
async def select_inst_remind(callback: CallbackQuery, state: FSMContext, db_path: str):
    await callback.answer()
    inst_id = int(callback.data.replace("remind_inst_", ""))
    
    # Get installment details for context
    data = await state.get_data()
    case_id = data.get("remind_case_id")
    installments = db.get_installments(db_path, case_id)
    selected_inst = next((i for i in installments if i['id'] == inst_id), None)
    
    if not selected_inst:
        await callback.message.edit_text("❌ خطا در یافتن قسط.")
        await state.clear()
        return
        
    await state.update_data(remind_inst_id=inst_id, remind_inst_idx=selected_inst['idx'], remind_inst_amount=selected_inst['amount'])
    
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    buttons = [
        [InlineKeyboardButton(text="بله", callback_data="remind_note_yes"), InlineKeyboardButton(text="خیر", callback_data="remind_note_no")],
        [InlineKeyboardButton(text="❌ انصراف", callback_data="cancel_installment_remind")]
    ]
    await state.set_state(InstallmentReminder.asking_for_note)
    await callback.message.edit_text(f"❓ آیا می‌خواهید توضیحات اضافه‌ای به پیام یادآوری قسط {selected_inst['idx']} اضافه کنید؟", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@router.callback_query(InstallmentReminder.asking_for_note, F.data == "remind_note_yes")
async def note_yes_remind(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(InstallmentReminder.entering_note)
    await callback.message.edit_text("📝 لطفا توضیحات خود را بنویسید:")

@router.callback_query(InstallmentReminder.asking_for_note, F.data == "remind_note_no")
async def note_no_remind(callback: CallbackQuery, state: FSMContext, bot: Bot, db_path: str):
    await callback.answer()
    await process_send_reminder(callback.message, state, bot, db_path, None)

@router.message(InstallmentReminder.entering_note)
async def handle_remind_note(message: Message, state: FSMContext, bot: Bot, db_path: str):
    note = message.text.strip()
    await process_send_reminder(message, state, bot, db_path, note)

async def process_send_reminder(message: Message, state: FSMContext, bot: Bot, db_path: str, note: str | None):
    data = await state.get_data()
    case_id = data.get("remind_case_id")
    lic_code = data.get("remind_lic_code")
    idx = data.get("remind_inst_idx")
    amount = data.get("remind_inst_amount")
    case = db.get_case(db_path, case_id)
    
    if not case:
        final_msg = "❌ خطا: پرونده یافت نشد."
        if isinstance(message, Message):
            await message.answer(final_msg)
        else:
            await message.edit_text(final_msg)
        await state.clear()
        return

    # Escape common Markdown characters in dynamic fields
    safe_client_name = case['client_name'].replace("_", "\\_").replace("*", "\\*").replace("`", "\\`").replace("[", "\\[")
    safe_case_id = str(case_id).replace("_", "\\_").replace("*", "\\*").replace("`", "\\`").replace("[", "\\[")
    
    remind_text = (
        f"💰 یادآوری پرداخت قسط\n\n"
        f"👤 کلاینت: {safe_client_name}\n"
        f"📂 پرونده: `{safe_case_id}`\n"
        f"🔢 شماره قسط: {idx}\n"
        f"💵 مبلغ: {amount}\n"
    )
    
    if note:
        remind_text += f"\n\n📝 توضیحات ادمین:\n{note}"
        
    remind_text += "\n\n🙏 لطفا نسبت به پرداخت این قسط اقدام نمایید."

    members = db.get_users_by_license(db_path, lic_code)
    sent = 0
    for m in members:
        try:
            await bot.send_message(m['user_id'], remind_text, parse_mode="Markdown")
            sent += 1
        except: pass
        
    final_msg = f"✅ یادآوری قسط {idx} با موفقیت برای {sent} نفر ارسال شد."
    if isinstance(message, Message):
        await message.answer(final_msg)
    else:
        await message.edit_text(final_msg)
        
    await state.clear()

@router.callback_query(F.data == "cancel_installment_remind")
async def cancel_remind(callback: CallbackQuery, state: FSMContext):
    await callback.answer("لغو شد")
    await state.clear()
    await callback.message.edit_text("❌ عملیات یادآوری لغو شد.")

@router.callback_query(F.data == "back_to_remind_type")
async def back_to_type(callback: CallbackQuery, state: FSMContext, db_path: str, cfg):
    await installment_reminder_start(callback.message, state, db_path, cfg)
    await callback.answer()

@router.callback_query(F.data == "back_to_remind_lics")
async def back_to_remind_lics(callback: CallbackQuery, state: FSMContext, db_path: str):
    data = await state.get_data()
    owner_type = data.get("remind_owner_type")
    # Simulate selecting owner type again to show license list
    callback.data = f"remind_type_{owner_type}"
    await select_owner_type_remind(callback, state, db_path)

@router.callback_query(F.data == "back_to_remind_cases")
async def back_to_remind_cases(callback: CallbackQuery, state: FSMContext, db_path: str):
    data = await state.get_data()
    lic_code = data.get("remind_lic_code")
    # Simulate selecting license again to show case list
    callback.data = f"remind_lic_{lic_code}"
    await select_lic_remind(callback, state, db_path)

@router.message(AdminManagement.entering_admin_id)
async def enter_admin_id(message: Message, state: FSMContext, db_path: str):
    try:
        user_id = int(message.text.strip())
        user = db.get_user(db_path, user_id)
        if not user:
            # اگر کاربر یافت نشد، او را به عنوان ادمین ثبت می‌کنیم
            db.upsert_user_on_license_join(db_path, user_id, "admin", f"Admin {user_id}", "")
            print(f"DEBUG: Created new user {user_id} as admin during 'Add Admin' process")
        
        db.set_admin_permissions(db_path, user_id, {
            "can_manage_licenses": 1,
            "can_manage_cases": 1,
            "can_change_status": 1,
            "can_view_phones": 1,
            "can_manage_tickets": 1,
            "can_reply_tickets": 1,
            "can_send_messages": 1,
            "can_broadcast": 1,
            "can_manage_interviews": 1,
            "can_manage_admins": 1,
        })
        with db.connect(db_path) as conn:
            conn.execute("UPDATE users SET role = 'admin' WHERE user_id = ?", (user_id,))
        await message.answer(f"✅ کاربر {user_id} به عنوان ادمین اضافه شد.", reply_markup=get_smart_kb(kb_admins_menu, message.from_user.id, db_path))
        await state.clear()
    except ValueError:
        await message.answer("لطفاً آیدی عددی را وارد کنید:")


@router.message(F.text == "🗑 حذف ادمین")
async def remove_admin_start(message: Message, state: FSMContext, db_path: str):
    admins = db.get_all_admin_users(db_path)
    if not admins:
        await message.answer("هیچ ادمینی وجود ندارد.")
        return
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    buttons = []
    for a in admins:
        name = a['full_name'] or f"آیدی: {a['user_id']}"
        role_badge = "⭐" if a['role'] == 'super_admin' else "🔑"
        buttons.append([InlineKeyboardButton(
            text=f"❌ حذف {role_badge} {name}",
            callback_data=f"admin_remove_{a['user_id']}"
        )])
    await message.answer("👇 ادمین مورد نظر برای حذف را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


@router.callback_query(F.data.startswith("admin_remove_"))
async def remove_admin_callback(callback: CallbackQuery, db_path: str):
    await callback.answer()
    user_id = int(callback.data.replace("admin_remove_", ""))
    with db.connect(db_path) as conn:
        conn.execute("UPDATE users SET role = 'direct_client' WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM admin_permissions WHERE user_id = ?", (user_id,))
    await callback.message.answer(f"✅ ادمین {user_id} با موفقیت حذف شد.", reply_markup=get_smart_kb(kb_admins_menu, callback.from_user.id, db_path))


@router.message(F.text == "👁 مشاهده ادمین‌ها")
async def view_admins(message: Message, db_path: str):
    admins = db.get_all_admin_users(db_path)
    if not admins:
        await message.answer("❌ هیچ ادمینی در سیستم ثبت نشده است.")
        return
    lines = ["👥 لیست ادمین‌های سیستم\n" + "━" * 25]
    for i, a in enumerate(admins, 1):
        role_emoji = "⭐" if a['role'] == 'super_admin' else "🔑"
        role_text = "سوپرادمین" if a['role'] == 'super_admin' else "ادمین"
        name = a['full_name'] or 'بدون نام'
        lines.append(
            f"\n{i}\\. {role_emoji} {role_text}\n"
            f"👤 نام: {name}\n"
            f"🆔 آیدی: `{a['user_id']}`"
        )
    lines.append("\n" + "━" * 25)
    await message.answer("\n".join(lines), reply_markup=get_smart_kb(kb_admins_menu, message.from_user.id, db_path), parse_mode="Markdown")


@router.message(F.text == "⚙️ ریست فکتوری")
async def factory_reset_start(message: Message, db_path: str, cfg):
    user = db.get_user(db_path, message.from_user.id)
    is_super_admin = (message.from_user.id == cfg.super_admin_id) or (user and user["role"] == "super_admin")
    if not is_super_admin:
        await message.answer("❌ این دستور فقط برای سوپر ادمین مجاز است.")
        return
    await message.answer("⚠️ هشدار بسیار مهم\n\nآیا مطمئن هستید که می‌خواهید کل دیتابیس را پاک کنید؟ تمام اطلاعات پرونده‌ها، لایسنس‌ها و کاربران حذف خواهد شد!", 
                         reply_markup=kb_yes_no("factory_reset_1"), parse_mode="Markdown")

@router.callback_query(F.data == "confirm_factory_reset_1_yes")
async def factory_reset_confirm_1(callback: CallbackQuery, db_path: str, cfg):
    user = db.get_user(db_path, callback.from_user.id)
    is_super_admin = (callback.from_user.id == cfg.super_admin_id) or (user and user["role"] == "super_admin")
    if not is_super_admin:
        await callback.answer("❌ عدم دسترسی", show_alert=True)
        return
    await callback.message.edit_text("🚨 تاییدیه دوم\n\nآیا واقعاً و ۱۰۰٪ مطمئن هستید؟ این عملیات غیرقابل بازگشت است!", 
                                     reply_markup=kb_yes_no("factory_reset_2"), parse_mode="Markdown")

@router.callback_query(F.data == "confirm_factory_reset_2_yes")
async def factory_reset_confirm_2(callback: CallbackQuery, db_path: str, cfg):
    user = db.get_user(db_path, callback.from_user.id)
    is_super_admin = (callback.from_user.id == cfg.super_admin_id) or (user and user["role"] == "super_admin")
    if not is_super_admin:
        await callback.answer("❌ عدم دسترسی", show_alert=True)
        return
    
    import os
    import sys
    
    await callback.message.edit_text("🔄 در حال پاکسازی دیتابیس و ریستارت ربات...")
    
    # Close connection if any and delete file
    if os.path.exists(db_path):
        os.remove(db_path)
    
    # Restart the bot
    os.execv(sys.executable, ['python'] + sys.argv)

@router.callback_query(F.data.startswith("confirm_factory_reset_"))
async def factory_reset_cancel(callback: CallbackQuery):
    if "_no" in callback.data:
        await callback.message.edit_text("❌ عملیات ریست فکتوری لغو شد.")

@router.message(F.text == "📱 تست پیامک")
async def sms_test_start(message: Message, state: FSMContext, cfg):
    if message.from_user.id != cfg.super_admin_id:
        return
    await state.set_state(SMSTest.entering_phone)
    await message.answer("📱 شماره موبایل کلاینت را جهت تست وارد کنید:\n(مثال: 09120000000)")


@router.message(SMSTest.entering_phone)
async def sms_test_phone(message: Message, state: FSMContext):
    phone = message.text.strip()
    if not sms_service.validate_phone_number(phone):
        await message.answer("❌ شماره نامعتبر است. لطفاً مجدداً وارد کنید:")
        return
    await state.update_data(test_phone=phone)
    await state.set_state(SMSTest.entering_message)
    await message.answer(f"💬 متن پیام تست را برای شماره {phone} وارد کنید:")


@router.message(SMSTest.entering_message)
async def sms_test_send(message: Message, state: FSMContext):
    text = message.text.strip()
    data = await state.get_data()
    phone = data["test_phone"]
    
    # Try sending
    success, result = sms_service.send_sms(phone, text)
    
    if success:
        await message.answer(f"✅ پیامک با موفقیت ارسال شد!\n`{result}`", parse_mode="Markdown")
        await state.clear()
    elif "2FA" in result or "code" in result.lower():
        await state.update_data(test_message=text)
        await state.set_state(SMSTest.waiting_for_2fa)
        await message.answer("🔐 کد تایید ورود دو مرحله‌ای ملی‌پیامک به شماره شما ارسال شد. لطفاً آن را وارد کنید:")
    else:
        await message.answer(f"❌ خطای ارسال پیامک:\n`{result}`", parse_mode="Markdown")
        await state.clear()


@router.message(SMSTest.waiting_for_2fa)
async def sms_test_2fa(message: Message, state: FSMContext):
    code = message.text.strip()
    data = await state.get_data()
    phone = data["test_phone"]
    text = data["test_message"]
    
    # Re-initialize with code
    success, result = sms_service._initialize_client(code=code)
    if success:
        # Retry send
        success_send, result_send = sms_service.send_sms(phone, text)
        if success_send:
            await message.answer(f"✅ ورود موفق و پیامک ارسال شد!\n`{result_send}`", parse_mode="Markdown")
        else:
            await message.answer(f"❌ ورود موفق بود اما ارسال فیل شد:\n`{result_send}`", parse_mode="Markdown")
    else:
        await message.answer(f"❌ کد تایید اشتباه یا منقضی شده است: {result}")
    
    await state.clear()


@router.message(F.text == "🔐 مدیریت دسترسی‌ها")
async def manage_permissions_start(message: Message, state: FSMContext, db_path: str):
    admins = db.get_all_admin_users(db_path)
    if not admins:
        await message.answer("هیچ ادمینی وجود ندارد.")
        return
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    buttons = []
    for a in admins:
        name = a['full_name'] or f"آیدی: {a['user_id']}"
        role_badge = "⭐" if a['role'] == 'super_admin' else "🔑"
        buttons.append([InlineKeyboardButton(
            text=f"{role_badge} {name}",
            callback_data=f"admin_perms_{a['user_id']}"
        )])
    await message.answer("🔐 ادمین مورد نظر را برای مدیریت دسترسی انتخاب کنید:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


@router.callback_query(F.data.startswith("admin_perms_"))
async def manage_permissions_callback(callback: CallbackQuery, db_path: str):
    await callback.answer()
    user_id = int(callback.data.replace("admin_perms_", ""))
    perms = db.get_admin_permissions(db_path, user_id)
    if not perms:
        await callback.message.answer("⚠️ این کاربر در جدول دسترسی‌ها ثبت نشده. ابتدا او را به عنوان ادمین اضافه کنید.")
        return
    from .keyboards import kb_admin_permissions
    user = db.get_user(db_path, user_id)
    name = user.get('full_name') or str(user_id) if user else str(user_id)
    await callback.message.answer(
        f"🔐 دسترسی‌های {name}\nبرای روشن/خاموش کردن هر دسترسی کلیک کنید:",
        reply_markup=kb_admin_permissions(user_id, perms),
        parse_mode="Markdown"
    )


@router.message(F.text == "⭐ سوپرادمین کردن")
async def make_super_admin_start(message: Message, db_path: str):
    admins = db.get_all_admin_users(db_path)
    if not admins:
        await message.answer("⚠️ هیچ ادمینی برای ارتقا وجود ندارد. ابتدا ادمین اضافه کنید.")
        return
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    buttons = []
    for a in admins:
        if a['role'] == 'super_admin':
            continue
        name = a['full_name'] or f"آیدی: {a['user_id']}"
        buttons.append([InlineKeyboardButton(
            text=f"⭐ ارتقا: 🔑 {name}",
            callback_data=f"admin_makesup_{a['user_id']}"
        )])
    if not buttons:
        await message.answer("همه ادمین‌ها از قبل سوپرادمین هستند.")
        return
    await message.answer("⭐ ادمینی که می‌خواهید سوپرادمین شود را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))






@router.callback_query(F.data == "enter_manual_license")
async def enter_manual_license_cb(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(Onboarding.waiting_for_license)
    await callback.message.answer("🔑 لطفا کد لایسنس خود را وارد کنید:")


@router.callback_query(F.data == "create_new_ticket")
async def create_new_ticket_cb(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(TicketManagement.entering_subject)
    await callback.message.answer("🎫 لطفا متن تیکت خود را وارد کنید:")


@router.message(F.text == "ایجاد تیکت")
async def create_ticket_start(message: Message, state: FSMContext):
    await state.set_state(TicketManagement.entering_subject)
    await message.answer("🎫 لطفا متن تیکت خود را وارد کنید:")


@router.message(TicketManagement.creating_ticket)
async def create_ticket_from_client(message: Message, state: FSMContext, bot: Bot, cfg, db_path: str):
    user = db.get_user(db_path, message.from_user.id)
    if not user:
        await message.answer("خطا در دسترسی.")
        return
    
    subject = message.text.strip()
    ticket_id = db.create_ticket(db_path, message.from_user.id, user["role"], subject)
    await message.answer(f"✅ تیکت شما با شماره #{ticket_id} ایجاد شد. منتظر پاسخ ادمین بمانید.", reply_markup=menu_for_role(user["role"], db_path, message.from_user.id))
    
    # Notify all admins with can_manage_tickets permission
    admins = db.get_users_by_role(db_path, "admin")
    notification_text = (
        f"<b>🎫 تیکت جدید!</b>\n\n"
        f"<b>🔢 شماره:</b> <code>#{ticket_id}</code>\n"
        f"<b>👤 از:</b> {user['role']} - {user.get('full_name', 'ناشناس')}\n"
        f"<b>📝 موضوع:</b> {subject}"
    )
    
    # Send to super admin
    await bot.send_message(cfg.super_admin_id, notification_text, reply_markup=kb_ticket_actions(ticket_id), parse_mode="HTML")
    
    # Send to other admins with permission
    admins = db.get_users_by_role(db_path, "admin")
    for admin in admins:
        if admin['user_id'] == cfg.super_admin_id: continue
        perms = db.get_admin_permissions(db_path, admin['user_id'])
        if perms and perms.get('can_manage_tickets'):
            try:
                await bot.send_message(admin['user_id'], notification_text, reply_markup=kb_ticket_actions(ticket_id), parse_mode="HTML")
            except:
                pass
    
    await state.clear()


@router.message(TicketManagement.entering_subject)
async def create_ticket(message: Message, state: FSMContext, db_path: str):
    user = db.get_user(db_path, message.from_user.id)
    if not user:
        await message.answer("خطا در دسترسی.")
        return
    ticket_id = db.create_ticket(db_path, message.from_user.id, user["role"], message.text.strip())
    await message.answer(f"✅ تیکت شما با شماره #{ticket_id} ایجاد شد.", reply_markup=menu_for_role(user["role"], db_path, message.from_user.id))
    await state.clear()


@router.message(TicketManagement.entering_reply)
async def ticket_reply(message: Message, state: FSMContext, bot: Bot, db_path: str, cfg):
    data = await state.get_data()
    ticket_id = data.get("ticket_id")
    if not ticket_id:
        await message.answer("❌ خطا. تیکت مشخص نیست.")
        await state.clear()
        return
    
    ticket = db.get_ticket(db_path, ticket_id)
    if not ticket:
        await message.answer("❌ تیکت یافت نشد.")
        await state.clear()
        return

    user = db.get_user(db_path, message.from_user.id)
    text = message.text.strip()
    
    db.add_ticket_message(db_path, ticket_id, message.from_user.id, user["role"], "text", text)
    
    if user["role"] in ("super_admin", "admin"):
        admin_name = user.get('full_name') or "ادمین مدیریت"
        try:
            await bot.send_message(
                ticket['created_by_user_id'],
                f"📨 پاسخ جدید از مدیریت!\n\n"
                f"👤 پاسخ‌دهنده: {admin_name}\n"
                f"🎫 تیکت: `#{ticket_id}`\n\n"
                f"💬 متن پاسخ:\n{text}",
                reply_markup=kb_user_ticket_actions(ticket_id),
                parse_mode="Markdown"
            )
            await message.answer("✅ پاسخ شما با موفقیت برای کاربر ارسال شد.")
        except:
            await message.answer(f"⚠️ پاسخ در سیستم ثبت شد کابر پیام را دریافت نکرد (احتمالا ربات را بلاک کرده)")
    else:
        await message.answer("✅ پیام شما با موفقیت برای تیم مدیریت ارسال شد. لطفاً منتظر بررسی بمانید.")
        target_admin = ticket['assigned_admin_id'] or cfg.super_admin_id
        notification_text = (
            f"📨 *پاسخ جدید به تیکت!*\n\n"
            f"🎫 تیکت: `#{ticket_id}`\n"
            f"👤 از: {user.get('full_name', 'ناشناس')}\n\n"
            f"💬 متن:\n{text}"
        )
        try:
            await bot.send_message(target_admin, notification_text, reply_markup=kb_ticket_actions(ticket_id), parse_mode="Markdown")
        except:
            pass

    await state.clear()


@router.callback_query(F.data.startswith("ticket_reply_"))
async def ticket_reply_start(callback: CallbackQuery, state: FSMContext, db_path: str):
    ticket_id = int(callback.data.replace("ticket_reply_", ""))
    ticket = db.get_ticket(db_path, ticket_id)
    
    if not ticket:
        await callback.answer("تیکت یافت نشد.")
        return

    admin_id = callback.from_user.id
    
    # Check if already assigned
    if ticket['assigned_admin_id'] and ticket['assigned_admin_id'] != admin_id:
        admin = db.get_user(db_path, ticket['assigned_admin_id'])
        name = admin.get('full_name') or f"ID: {ticket['assigned_admin_id']}"
        await callback.message.answer(f"⚠️ این تیکت قبلاً توسط ادمین *{name}* در حال پیگیری است.", parse_mode="Markdown")
        await callback.answer()
        return

    # Claim the ticket
    db.claim_ticket(db_path, ticket_id, admin_id)
    await state.update_data(ticket_id=ticket_id)
    await state.set_state(TicketManagement.entering_reply)
    await callback.message.answer(f"📝 پاسخ خود را برای تیکت #{ticket_id} وارد کنید:")
    await callback.answer()


@router.callback_query(F.data.startswith("ticket_close_"))
async def ticket_close(callback: CallbackQuery, bot: Bot, db_path: str, cfg):
    data = callback.data
    # Extract ID reliably from end
    try:
        ticket_id = int(data.split("_")[-1])
    except:
        await callback.answer("❌ شناسه تیکت نامعتبر است.")
        return

    ticket = db.get_ticket(db_path, ticket_id)
    if not ticket:
        await callback.answer("تیکت یافت نشد.")
        return

    db.close_ticket(db_path, ticket_id)
    await callback.message.edit_text(f"🔒 تیکت #{ticket_id} بسته شد.")
    
    # Notify other party
    user = db.get_user(db_path, callback.from_user.id)
    if user['role'] in ('admin', 'super_admin'):
        # Admin closed it, notify the client
        try:
            await bot.send_message(
                ticket['created_by_user_id'],
                f"🔒 تیکت شماره `#{ticket_id}` توسط تیم مدیریت بسته شد.",
                parse_mode="Markdown"
            )
        except: pass
    else:
        # User closed it, notify assigned admin or super admin
        target_id = ticket['assigned_admin_id'] or cfg.super_admin_id
        try:
            name = user.get('full_name') or f"آیدی {user['user_id']}"
            await bot.send_message(
                target_id,
                f"🔒 تیکت شماره `#{ticket_id}` توسط کاربر ({name}) بسته شد.",
                parse_mode="Markdown"
            )
        except: pass
    await callback.answer()


@router.message(InterviewManagement.selecting_case)
async def select_case_for_interview(message: Message, state: FSMContext, db_path: str):
    case_id = message.text.strip()
    case = db.get_case(db_path, case_id)
    if not case:
        await message.answer("پرونده یافت نشد.")
        return
    await state.update_data(interview_case_id=case_id)
    await state.set_state(InterviewManagement.entering_email_text)
    await message.answer("ایمیل یا متن مصاحبه را وارد کنید:")


async def process_interview_text(message_or_callback, state: FSMContext, raw_text: str, case_id: str, db_path: str):
    interview_id = db.create_interview(db_path, case_id, raw_text)
    await state.update_data(interview_id=interview_id)
    
    from .config import load_config
    cfg = load_config()
    
    extracted = {"scheduled_at_iso": None, "meeting_link": None, "employer_name": None, "company_name": None, "city": None, "platform": None, "username": None, "password": None}
    if cfg.vertex_service_account_json and cfg.vertex_project_id:
        try:
            import vertexai
            from vertexai.generative_models import GenerativeModel
            vertexai.init(project=cfg.vertex_project_id, location=cfg.vertex_location)
            model = GenerativeModel(cfg.vertex_model)
            prompt = f"""Extract interview details from this email. 
Return ONLY a valid JSON object with these keys: 
- scheduled_at_iso (ISO 8601 format, e.g., '2026-02-03T09:00:00Z')
- meeting_link (The FULL Zoom/Teams/etc URL)
- employer_name (Person's name)
- company_name (Company name)
- city (Location)
- platform (Zoom, Google Meet, etc)
- username (If Meeting-ID is present, use it as username)
- password (If Kenncode or Password is present)

If a field is missing, use null.
The email mentions: "Tuesday Feb 3, 2026 ⋅ 9am – 9:30am (Coordinated Universal Time)". Convert to ISO.

Email content:
{raw_text}
"""
            response = model.generate_content(prompt)
            text = response.text
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()
            
            if "{" in text and "}" in text:
                json_str = text[text.find("{"):text.rfind("}")+1]
                extracted_data = json.loads(json_str)
                for key in extracted:
                    if key in extracted_data:
                        extracted[key] = extracted_data[key]
        except Exception as e:
            pass
    db.update_interview(db_path, interview_id, {"extracted_json": json.dumps(extracted), **extracted})
    
    # After extraction, ask for major/field selection
    await ask_interview_major(message_or_callback, state, case_id, interview_id, db_path)

async def ask_interview_major(message_or_callback, state: FSMContext, case_id: str, interview_id: int, db_path: str):
    fields = db.get_case_fields(db_path, case_id)
    if not fields:
        # If no fields found, skip to summary (shouldn't happen with new system but for safety)
        target = message_or_callback.message if hasattr(message_or_callback, 'message') else message_or_callback
        await show_interview_summary(target, interview_id, db_path, state)
        return

    from .keyboards import kb_field_selection
    text = "🎓 این مصاحبه مربوط به کدام رشته است؟\nلطفاً انتخاب کنید:"
    
    target = message_or_callback.message if hasattr(message_or_callback, 'message') else message_or_callback
    await state.set_state(InterviewManagement.selecting_field)
    await state.update_data(interview_id=interview_id)
    
    if hasattr(message_or_callback, 'message'):
        await message_or_callback.message.edit_text(text, reply_markup=kb_field_selection(fields, "iv_field_"))
    else:
        await message_or_callback.answer(text, reply_markup=kb_field_selection(fields, "iv_field_"))

@router.callback_query(InterviewManagement.selecting_field, F.data.startswith("iv_field_"))
async def interview_field_selected(callback: CallbackQuery, state: FSMContext, db_path: str):
    field_id = int(callback.data.replace("iv_field_", ""))
    field = db.get_case_field(db_path, field_id)
    
    data = await state.get_data()
    interview_id = data.get("interview_id")
    
    if field and interview_id:
        # We'll store the field name in a new column or just in the JSON for now
        # Actually, let's add a column 'field_name' to interviews table in db.py later
        # For now, we update the extracted_json to include it
        iv = db.get_interview(db_path, interview_id)
        if iv:
            extracted = json.loads(iv['extracted_json']) if iv.get('extracted_json') else {}
            extracted['selected_field'] = field['field_name']
            db.update_interview(db_path, interview_id, {"extracted_json": json.dumps(extracted)})
            
    await callback.answer(f"✅ رشته {field['field_name']} انتخاب شد.")
    await show_interview_summary(callback.message, interview_id, db_path, state)


@router.message(InterviewManagement.entering_email_text)
async def process_interview_email(message: Message, state: FSMContext, db_path: str, cfg):
    data = await state.get_data()
    case_id = data.get("interview_case_id")
    raw_text = message.text.strip()
    await process_interview_text(message, state, raw_text, case_id, db_path)


@router.callback_query(F.data.startswith("confirm_iv_"))
async def confirm_iv_extraction(callback: CallbackQuery, db_path: str, bot: Bot):
    iv_id = int(callback.data.replace("confirm_iv_", ""))
    
    # Get interview details before confirmation to ensure we have the data
    iv = db.get_interview(db_path, iv_id)
    if not iv:
        await callback.answer("❌ مصاحبه یافت نشد.")
        return

    # Update status to confirmed
    db.update_interview(db_path, iv_id, {"status": "confirmed"})
    
    # Notify case owner
    case = db.get_case(db_path, iv["case_id"])
    if case:
        users = db.get_users_by_license(db_path, case["owner_license_code"])
        
        # Format date for display
        display_date = iv.get('scheduled_at_iso', '-')
        if display_date and 'T' in display_date:
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(display_date.replace('Z', '+00:00'))
                display_date = dt.strftime("%Y-%m-%d %H:%M")
            except:
                pass

        # Get selected field
        extracted = json.loads(iv['extracted_json']) if iv.get('extracted_json') else {}
        selected_field = extracted.get('selected_field', '')
        field_suffix = f" ({selected_field})" if selected_field else ""

        msg_text = f"📅 مصاحبه جدید ثبت شد{field_suffix}\n\n"
        msg_text += f"📋 پرونده: {case['case_id']} | {case['client_name']}\n"
        msg_text += f"🏢 شرکت: {iv.get('company_name', '-')}\n"
        msg_text += f"👤 کارفرما: {iv.get('employer_name', '-')}\n"
        msg_text += f"🌐 پلتفرم: {iv.get('platform', '-')}\n"
        msg_text += f"📅 تاریخ: {display_date} (به وقت آلمان)\n\n"
        
        kb = None
        meeting_link = iv.get('meeting_link')
        if meeting_link and meeting_link.startswith("http"):
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔗 ورود به جلسه", url=meeting_link)]
            ])
        
        for u in users:
            try:
                # Use MarkdownV2 for better telegram compatibility or stick to Markdown
                await bot.send_message(u["user_id"], msg_text, reply_markup=kb, parse_mode="Markdown")
            except:
                pass

    # Notify user and admin if interview is mapped to an installment
    mapped_insts = db.get_mapped_installments(db_path, iv["case_id"], "interview")
    for inst in mapped_insts:
        if not inst.get("is_paid", False):
            db.add_pending_reminder(db_path, iv["case_id"], inst["id"], "interview")

    await callback.message.edit_text("✅ مصاحبه با موفقیت تایید و در تقویم ثبت شد.")
    await callback.answer()


@router.message(F.text == "تایید مصاحبه")
async def confirm_interview(message: Message, state: FSMContext, db_path: str, bot: Bot):
    data = await state.get_data()
    interview_id = data.get("interview_id")
    if interview_id:
        # Get interview details before confirmation
        iv = db.get_interview(db_path, interview_id)
        if not iv:
            await message.answer("❌ مصاحبه یافت نشد.")
            await state.clear()
            return

        db.update_interview(db_path, interview_id, {"status": "confirmed"})
        
        # Notify case owner
        case = db.get_case(db_path, iv["case_id"])
        if case:
            users = db.get_users_by_license(db_path, case["owner_license_code"])
            
            # Format date for display
            display_date = iv.get('scheduled_at_iso', '-')
            if display_date and 'T' in display_date:
                try:
                    from datetime import datetime
                    dt = datetime.fromisoformat(display_date.replace('Z', '+00:00'))
                    display_date = dt.strftime("%Y-%m-%d %H:%M")
                except:
                    pass

        # Get selected field
        extracted = json.loads(iv['extracted_json']) if iv.get('extracted_json') else {}
        selected_field = extracted.get('selected_field', '')
        field_suffix = f" ({selected_field})" if selected_field else ""

        msg_text = f"📅 مصاحبه جدید ثبت شد{field_suffix}\n\n"
        msg_text += f"📋 پرونده: {case['case_id']} | {case['client_name']}\n"
        msg_text += f"🏢 شرکت: {iv.get('company_name', '-')}\n"
        msg_text += f"👤 کارفرما: {iv.get('employer_name', '-')}\n"
        msg_text += f"🌐 پلتفرم: {iv.get('platform', '-')}\n"
        msg_text += f"📅 تاریخ: {display_date} (به وقت آلمان)\n\n"
        
        kb = None
        meeting_link = iv.get('meeting_link')
        if meeting_link and meeting_link.startswith("http"):
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔗 ورود به جلسه", url=meeting_link)]
            ])
        
        for u in users:
            try:
                await bot.send_message(u["user_id"], msg_text, reply_markup=kb, parse_mode="Markdown")
            except:
                pass
            kb = None
            meeting_link = iv.get('meeting_link')
            if meeting_link and meeting_link.startswith("http"):
                kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔗 ورود به جلسه", url=meeting_link)]
                ])
            
            for u in users:
                try:
                    await bot.send_message(u["user_id"], msg_text, reply_markup=kb, parse_mode="Markdown")
                except:
                    pass

        await message.answer("✅ مصاحبه تایید شد.", reply_markup=get_smart_kb(kb_interviews_menu, message.from_user.id, db_path))
    await state.clear()


@router.message(F.text == "مدارک")
async def documents_menu(message: Message, state: FSMContext, db_path: str):
    user = db.get_user(db_path, message.from_user.id)
    if user and user.get("license_code"):
        cases = db.get_all_cases(db_path, user["license_code"])
    else:
        cases = db.get_all_cases(db_path)
    if not cases:
        await message.answer("هیچ پرونده‌ای وجود ندارد.")
        return
    text = "پرونده را انتخاب کنید:\n\n"
    for c in cases[:10]:
        text += f"- {c['case_id']} | {c['client_name']}\n"
    await message.answer(text, reply_markup=kb_back_main())


@router.message(DocumentUpload.selecting_case)
async def select_case_for_docs(message: Message, state: FSMContext, db_path: str):
    case_id = message.text.strip()
    case = db.get_case(db_path, case_id)
    if not case:
        await message.answer("❌ پرونده یافت نشد.")
        return
    await state.update_data(doc_case_id=case_id, doc_index=0)
    db.create_document_request(db_path, case_id)
    await show_next_doc_request(message, state, case_id, db_path)


async def show_next_doc_request(message: Message, state: FSMContext, case_id: str, db_path: str):
    data = await state.get_data()
    idx = data.get("doc_index", 0)
    
    user = db.get_user(db_path, message.from_user.id if hasattr(message, 'from_user') else message.chat.id)
    user_role = user["role"] if user else "direct_client"
    
    docs = AGENCY_DOCS if user_role == "agency" else CLIENT_DOCS
    
    if idx >= len(docs):
        # Limit extra documents to 3
        temp_docs = data.get("temp_uploaded_docs", [])
        extra_docs_count = sum(1 for d in temp_docs if d["doc_type"] == "مدرک اضافی")
        
        if extra_docs_count >= 3:
            await message.answer("✅ تمام مدارک مورد نیاز و حداکثر مدارک اضافی (۳ عدد) ارسال شده‌اند.\n\nلطفاً تایید نهایی کنید.", reply_markup=kb_document_submit())
        else:
            await message.answer("✅ تمام مدارک مورد نیاز بررسی شدند.\n\nمی‌توانید مدارک اضافی بفرستید (حداکثر ۳ عدد) یا تایید نهایی کنید.", reply_markup=kb_document_submit())
        
        await state.set_state(DocumentUpload.adding_extra_docs)
        return
        
    doc_type = docs[idx]
    await state.update_data(current_doc_type=doc_type)
    text = f"📄 *مدرک {idx+1} از {len(docs)}: {doc_type}*\n\nآیا این مدرک را برای ارسال آماده دارید؟"
    await message.answer(text, reply_markup=kb_document_upload(), parse_mode="Markdown")
    await state.set_state(DocumentUpload.uploading_doc)


@router.message(DocumentUpload.uploading_doc, F.text == "📤 ارسال فایل")
async def ask_for_file(message: Message, state: FSMContext):
    data = await state.get_data()
    doc_type = data.get("current_doc_type", "مدرک")
    await message.answer(f"📥 لطفاً فایل یا تصویر مربوط به *{doc_type}* را همینجا ارسال کنید:", parse_mode="Markdown")


@router.message(DocumentUpload.uploading_doc, F.text == "❌ این مدرک را ندارم")
async def skip_doc_start(message: Message, state: FSMContext, db_path: str):
    await message.answer("💬 لطفاً دلیل نداشتن این مدرک را به صورت کوتاه بنویسید:")
    await state.update_data(waiting_for_skip_reason=True)


@router.message(DocumentUpload.uploading_doc, F.photo | F.document)
async def handle_doc_upload(message: Message, state: FSMContext, db_path: str):
    data = await state.get_data()
    case_id = data.get("doc_case_id")
    doc_type = data.get("current_doc_type")
    idx = data.get("doc_index", 0)
    
    file_id = None
    file_name = doc_type
    
    # Check file format restrictions
    is_image = message.photo is not None
    is_pdf = message.document and message.document.mime_type == "application/pdf"
    
    allowed_images = ["عکس پاسپورت", "عکس شخص", "عکس امضا"]
    
    if doc_type in allowed_images:
        if not (is_image or is_pdf):
            await message.answer("❌ برای این مدرک فقط فرمت‌های عکس (JPG, PNG) یا PDF مجاز است.")
            return
    else:
        if not is_pdf:
            await message.answer("❌ این مدرک فقط و فقط باید با فرمت PDF ارسال شود.")
            return

    if message.photo:
        file_id = message.photo[-1].file_id
    elif message.document:
        file_id = message.document.file_id
        file_name = message.document.file_name
    
    # Store in temporary state instead of DB
    temp_docs = data.get("temp_uploaded_docs", [])
    temp_docs.append({
        "doc_type": doc_type,
        "file_id": file_id,
        "file_name": file_name,
        "uploaded_by": message.from_user.id
    })
    
    await message.answer(f"✅ مدرک *{doc_type}* با موفقیت دریافت شد.", parse_mode="Markdown")
    
    await state.update_data(temp_uploaded_docs=temp_docs, doc_index=idx + 1)
    await show_next_doc_request(message, state, case_id, db_path)


@router.message(DocumentUpload.uploading_doc, F.text)
async def handle_doc_skip_reason(message: Message, state: FSMContext, db_path: str):
    data = await state.get_data()
    case_id = data.get("doc_case_id")
    
    if data.get("waiting_for_skip_reason"):
        doc_type = data.get("current_doc_type")
        idx = data.get("doc_index", 0)
        reason = message.text.strip()
        
        # Store skip in temporary state instead of DB
        temp_docs = data.get("temp_uploaded_docs", [])
        temp_docs.append({
            "doc_type": doc_type,
            "file_id": None,
            "file_name": f"SKIP: {reason}",
            "uploaded_by": message.from_user.id
        })
        
        await message.answer(f"✅ دلیل عدم ارسال مدرک *{doc_type}* ثبت شد.", parse_mode="Markdown")
        await state.update_data(temp_uploaded_docs=temp_docs, doc_index=idx + 1, waiting_for_skip_reason=False)
        await show_next_doc_request(message, state, case_id, db_path)
    else:
        # User might have typed something else or just the skip reason after clicking the button
        # (This depends on how the state machine handles it, but let's be safe)
        pass


@router.message(DocumentUpload.adding_extra_docs, F.photo | F.document)
async def handle_extra_doc_upload(message: Message, state: FSMContext, db_path: str):
    data = await state.get_data()
    doc_type = "مدرک اضافی"
    
    file_id = message.photo[-1].file_id if message.photo else message.document.file_id
    file_name = message.document.file_name if message.document else "extra_doc.jpg"
        
    # Store in temporary state instead of DB
    temp_docs = data.get("temp_uploaded_docs", [])
    temp_docs.append({
        "doc_type": doc_type,
        "file_id": file_id,
        "file_name": file_name,
        "uploaded_by": message.from_user.id
    })
    
    await state.update_data(temp_uploaded_docs=temp_docs)
    await message.answer("✅ مدرک اضافی ثبت شد. می‌توانید باز هم بفرستید یا تایید نهایی کنید.", reply_markup=kb_document_submit())


@router.message(F.text == "✅ تایید و ارسال برای بررسی")
@router.message(F.text == "تایید و ارسال برای بررسی")
async def submit_docs(message: Message, state: FSMContext, db_path: str):
    data = await state.get_data()
    case_id = data.get("doc_case_id")
    temp_docs = data.get("temp_uploaded_docs", [])
    
    if not case_id:
        await message.answer("❌ خطا: پرونده یافت نشد.")
        await state.clear()
        return

    if not temp_docs:
        await message.answer("⚠️ هیچ مدرکی برای ارسال وجود ندارد.")
        return

    # Now save everything to the database at once
    for doc in temp_docs:
        db.add_case_document(
            db_path, 
            case_id, 
            doc["doc_type"], 
            doc["file_id"], 
            doc["file_name"], 
            doc["uploaded_by"]
        )
        
    db.submit_document_request(db_path, case_id)
    
    # Notify super admin
    user = db.get_user(db_path, message.from_user.id)
    from .config import load_config
    cfg = load_config()
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    admin_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📥 دریافت و بررسی مدارک", callback_data=f"rev_case_{case_id}")]
    ])
    await message.bot.send_message(
        cfg.super_admin_id,
        f"🔔 *مدارک جدید برای بررسی!*\n\n"
        f"📂 پرونده: `{case_id}`\n"
        f"👤 توسط: {user['full_name']}\n\n"
        f"برای شروع بررسی روی دکمه زیر کلیک کنید:",
        parse_mode="Markdown",
        reply_markup=admin_kb
    )
    
    await message.answer(
        "✅ مدارک با موفقیت برای تیم بررسی ارسال شد. نتیجه از طریق همین ربات به شما اطلاع‌رسانی می‌شود.", 
        reply_markup=menu_for_role(user["role"], db_path, message.from_user.id)
    )
    await state.clear()


@router.message(F.text == "بررسی مدارک")
async def review_docs_start(message: Message, state: FSMContext, db_path: str):
    user = db.get_user(db_path, message.from_user.id)
    if user["role"] != "super_admin":
        await message.answer("❌ این بخش فقط برای سوپرادمین در دسترس است.")
        return
        
    with db.connect(db_path) as conn:
        rows = conn.execute("SELECT case_id, status FROM document_requests WHERE status = 'submitted'").fetchall()
    if not rows:
        await message.answer("✅ در حال حاضر پرونده‌ای برای بررسی مدارک وجود ندارد.")
        return
        
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    buttons = []
    for r in rows:
        buttons.append([InlineKeyboardButton(text=f"📂 بررسی مدارک: {r['case_id']}", callback_data=f"rev_case_{r['case_id']}")])
    
    await message.answer("📋 لیست پرونده‌های منتظر بررسی:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


@router.callback_query(F.data.startswith("rev_case_"))
async def start_reviewing_case(callback: CallbackQuery, state: FSMContext, db_path: str):
    case_id = callback.data.replace("rev_case_", "")
    docs = db.get_case_documents(db_path, case_id)
    if not docs:
        await callback.answer("مدرکی یافت نشد.")
        return
        
    await state.update_data(review_case_id=case_id)
    await callback.message.answer(f"🧐 شروع بررسی مدارک پرونده {case_id}...")
    await show_next_review_doc(callback.message, state, db_path)


async def show_next_review_doc(message: Message, state: FSMContext, db_path: str):
    data = await state.get_data()
    case_id = data.get("review_case_id")
    docs = [d for d in db.get_case_documents(db_path, case_id) if d['status'] == 'pending']
    
    if not docs:
        # All pending docs reviewed, summarize and notify user automatically
        all_docs = db.get_case_documents(db_path, case_id)
        rejected_docs = [d for d in all_docs if d['status'] == 'rejected']
        approved_docs = [d for d in all_docs if d['status'] == 'approved']
        
        case = db.get_case(db_path, case_id)
        if not case:
            await message.answer(f"❌ خطا: پرونده {case_id} در دیتابیس یافت نشد.")
            await state.clear()
            return

        owner_type_display = "موسسه" if case['owner_type'] == 'agency' else "کلاینت"
        
        if rejected_docs:
            db.reject_document_request(db_path, case_id, message.from_user.id if hasattr(message, 'from_user') else 0)
            status_text = "❌ رد شد (نیاز به اصلاح)"
            
            rejection_details = ""
            for rd in rejected_docs:
                rejection_details += f"🔹 *{rd['doc_type']}*: {rd['rejection_reason'] or 'نیاز به بررسی مجدد'}\n"
                
            user_msg = (
                f"⚠️ اطلاعیه مدارک: پرونده {case_id}\n\n"
                f"متاسفانه برخی از مدارک ارسالی شما مورد تایید قرار نگرفت.\n\n"
                f"📋 جزئیات مدارک رد شده: \n{rejection_details}\n"
                f"🔄 لطفاً مجدداً نسبت به آپلود مدارک اصلاح شده اقدام نمایید."
            )
        else:
            db.approve_document_request(db_path, case_id, message.from_user.id if hasattr(message, 'from_user') else 0)
            status_text = "✅ تایید نهایی شد"
            user_msg = (
                f"🎉 *مدارک تایید شد!*\n\n"
                f"✅ تمامی مدارک ارسالی شما برای پرونده `{case_id}` مورد تایید قرار گرفت و پرونده در جریان قرار گرفت.\n"
                f"🙏 از همکاری شما سپاسگزاریم."
            )

        # Notify User/Agency
        members = db.get_users_by_license(db_path, case['owner_license_code'])
        for m in members:
            try:
                await message.bot.send_message(m['user_id'], user_msg, parse_mode="Markdown")
            except: pass

        # Inform Admin
        await message.answer(
            f"🏁 *بررسی مدارک به پایان رسید*\n\n"
            f"📂 پرونده: `{case_id}`\n"
            f"📌 وضعیت نهایی: {status_text}\n"
            f"📢 نتیجه به {owner_type_display} اطلاع‌رسانی شد.",
            parse_mode="Markdown"
        )
        await state.clear()
        return
        
    doc = docs[0]
    text = f"� مدرک: {doc['doc_type']}\n👤 آپلود کننده: {doc['uploaded_by_user_id']}"
    
    from .keyboards import kb_document_review
    if doc['file_id']:
        if doc['file_name'].lower().endswith(('.jpg', '.jpeg', '.png')):
            await message.answer_photo(doc['file_id'], caption=text, reply_markup=kb_document_review(doc['id']))
        else:
            await message.answer_document(doc['file_id'], caption=text, reply_markup=kb_document_review(doc['id']))
    else:
        await message.answer(f"⚠️ {text}\n❌ کاربر این مدرک را ندارد.\nتوضیح: {doc['file_name']}", reply_markup=kb_document_review(doc['id']))


@router.callback_query(F.data.startswith("doc_approve_"))
async def approve_doc_rev(callback: CallbackQuery, state: FSMContext, db_path: str, bot: Bot):
    # Answer callback immediately to avoid Telegram timeout during GDrive auth/upload
    try:
        await callback.answer("⏳ در حال پردازش و آپلود...")
    except:
        pass

    doc_id = int(callback.data.replace("doc_approve_", ""))
    db.update_document_status(db_path, doc_id, "approved")
    
    # Check if doc has a file_id (not skipped)
    has_file = False
    with db.connect(db_path) as conn:
        doc_check = conn.execute("SELECT file_id FROM case_documents WHERE id = ?", (doc_id,)).fetchone()
        if doc_check and doc_check['file_id']:
            has_file = True

    # GDrive Upload Logic (Only if there's a file)
    if has_file:
        try:
            with db.connect(db_path) as conn:
                doc_row = conn.execute("SELECT * FROM case_documents WHERE id = ?", (doc_id,)).fetchone()
                if not doc_row:
                    await callback.message.answer("❌ خطا: مدرک یافت نشد.")
                    return
                
                doc = dict(doc_row)
                case_id = doc['case_id']
                # Update state with case_id to ensure show_next_review_doc works
                await state.update_data(review_case_id=case_id)
                
                case = db.get_case(db_path, case_id)
                if not case:
                    await callback.message.answer(f"❌ خطا: پرونده {case_id} یافت نشد.")
                    return

                lic = db.get_license(db_path, case['owner_license_code'])
                
                # Init GDrive
                gdrive = GDriveService(
                    credentials_path=r"C:\Users\Kasra\Desktop\bot\gdrive_credentials.json",
                    token_path=r"C:\Users\Kasra\Desktop\bot\gdrive_token.json"
                )
                
                # Root Folders
                parent_root_id = "16v72-SR6iAb9YsS2is4B8RyzC3CfbDcn"
                root_folder_name = "موسسات" if case['owner_type'] == 'agency' else "کلاینت ها"
                root_folder_id = gdrive.get_or_create_folder(root_folder_name, parent_id=parent_root_id)
                
                # Institution/Client Folder
                institution_name = lic.agency_name if lic and lic.agency_name else (lic.code if lic else "Unknown")
                parent_folder_id = gdrive.get_or_create_folder(institution_name, parent_id=root_folder_id)
                
                # Case Folder
                case_name = f"{case['client_name']} ({case['case_id']})"
                case_folder_id = gdrive.get_or_create_folder(case_name, parent_id=parent_folder_id)
                
                # Check for duplicate file
                doc_type = doc['doc_type']
                german_name = DOC_TYPE_MAPPING.get(doc_type)
                
                if german_name:
                    extension = ".pdf" if (doc['file_name'] or "").lower().endswith('.pdf') else ".jpg"
                    final_file_name = f"{german_name}{extension}"
                else:
                    final_file_name = doc['file_name'] or f"{doc['doc_type']}.jpg"

                existing_files = gdrive.find_file(final_file_name, case_folder_id)
                if existing_files:
                    await callback.message.answer(f"⚠️ فایل «{final_file_name}» قبلاً به درایو اضافه شده است و تکراری می‌باشد، لذا از آپلود مجدد آن صرف‌نظر شد.")
                else:
                    # Download from Telegram
                    file = await bot.get_file(doc['file_id'])
                    file_path = file.file_path
                    file_content = await bot.download_file(file_path)
                    content_bytes = file_content.read()
                    
                    # Upload to GDrive
                    mime_type = "application/pdf" if final_file_name.lower().endswith('.pdf') else "image/jpeg"
                    uploaded_file = await gdrive.upload_file(
                        file_content=content_bytes,
                        file_name=final_file_name,
                        folder_id=case_folder_id,
                        mime_type=mime_type
                    )
                    
                    link = uploaded_file.get('webViewLink')
                    if link:
                        await callback.message.answer(f"✅ مدرک «{doc['doc_type']}» با موفقیت در گوگل درایو ذخیره شد.\n🔗 [مشاهده در درایو]({link})", parse_mode="Markdown")
        except Exception as e:
            await callback.message.answer(f"⚠️ خطا در آپلود به گوگل درایو: {str(e)}")
            import traceback
            traceback.print_exc()
    else:
        # For skipped docs, just ensure state is updated
        with db.connect(db_path) as conn:
            doc_row = conn.execute("SELECT case_id FROM case_documents WHERE id = ?", (doc_id,)).fetchone()
            if doc_row:
                await state.update_data(review_case_id=doc_row['case_id'])

    await callback.message.delete()
    await show_next_review_doc(callback.message, state, db_path)


@router.callback_query(F.data.startswith("final_approve_"))
async def final_approve_docs(callback: CallbackQuery, state: FSMContext, db_path: str):
    case_id = callback.data.replace("final_approve_", "").replace("_yes", "").replace("_no", "")
    if "_yes" in callback.data:
        db.approve_document_request(db_path, case_id, callback.from_user.id)
        await callback.message.edit_text(f"✅ مدارک پرونده {case_id} به طور کامل تایید شد.")
        # Notify user (owner of the case)
        case = db.get_case(db_path, case_id)
        owner_license = case['owner_license_code']
        members = db.get_users_by_license(db_path, owner_license)
        
        # Determine receiver type for better messaging
        owner_type_display = "موسسه" if case['owner_type'] == 'agency' else "کلاینت"
        msg = (
            f"🎉 *مدارک تایید شد!*\n\n"
            f"✅ تمام مدارک ارسالی شما برای پرونده `{case_id}` توسط مدیریت تایید گردید.\n"
            f"🙏 از همکاری شما سپاسگزاریم."
        )
        
        for m in members:
            try:
                await callback.message.bot.send_message(m['user_id'], msg, parse_mode="Markdown")
            except: pass
    else:
        db.reject_document_request(db_path, case_id, callback.from_user.id)
        await callback.message.edit_text(f"❌ مدارک پرونده {case_id} رد شد.")
        
        # Notify user about overall rejection
        case = db.get_case(db_path, case_id)
        members = db.get_users_by_license(db_path, case['owner_license_code'])
        
        # Get rejected docs with reasons
        all_docs = db.get_case_documents(db_path, case_id)
        rejected_list = [d for d in all_docs if d['status'] == 'rejected']
        
        rejection_details = ""
        for rd in rejected_list:
            rejection_details += f"🔹 *{rd['doc_type']}*: {rd['rejection_reason'] or 'نیاز به بررسی مجدد'}\n"
            
        msg = (
            f"⚠️ *مدارک رد شد*\n\n"
            f"❌ متاسفانه برخی از مدارک ارسالی شما برای پرونده `{case_id}` مورد تایید قرار نگرفت.\n\n"
            f"📋 *دلایل رد:* \n{rejection_details}\n"
            f"🔄 لطفاً مجدداً نسبت به آپلود مدارک درخواستی اقدام نمایید."
        )
        
        for m in members:
            try:
                await callback.message.bot.send_message(m['user_id'], msg, parse_mode="Markdown")
            except: pass

@router.callback_query(F.data.startswith("case_fields_mgmt_"))
async def handle_fields_management(callback: CallbackQuery, db_path: str):
    case_id = callback.data.replace("case_fields_mgmt_", "")
    fields = db.get_case_fields(db_path, case_id)
    from .keyboards import kb_field_management
    await callback.message.edit_text(
        f"🎓 مدیریت رشته‌های پرونده `{case_id}`\n\nدر این بخش می‌توانید رشته‌های جدید اضافه کنید یا رشته‌های فعلی را حذف نمایید.",
        reply_markup=kb_field_management(case_id, fields)
    )
    await callback.answer()

@router.callback_query(F.data.startswith("field_add_new_"))
async def start_add_new_field(callback: CallbackQuery, state: FSMContext):
    case_id = callback.data.replace("field_add_new_", "")
    await state.update_data(mgmt_case_id=case_id)
    await state.set_state(CaseManagement.adding_new_field)
    await callback.message.answer(f"📍 نام رشته جدید برای پرونده `{case_id}` را وارد کنید:")
    await callback.answer()

@router.message(CaseManagement.adding_new_field, F.text)
async def handle_new_field_entry(message: Message, state: FSMContext, db_path: str):
    field_name = message.text.strip()
    data = await state.get_data()
    case_id = data.get("mgmt_case_id")
    
    if not case_id:
        await message.answer("❌ خطا در شناسایی پرونده. مجدداً تلاش کنید.")
        await state.clear()
        return

    db.add_case_field(db_path, case_id, field_name)
    await message.answer(f"✅ رشته «{field_name}» با موفقیت به پرونده اضافه شد.", reply_markup=get_smart_kb(kb_cases_menu, message.from_user.id, db_path))
    await state.clear()

@router.callback_query(F.data.startswith("field_del_"))
async def confirm_field_delete(callback: CallbackQuery, db_path: str):
    parts = callback.data.split("_")
    field_id = parts[2]
    case_id = parts[3]
    
    field = db.get_case_field(db_path, int(field_id))
    if not field:
        await callback.answer("❌ رشته یافت نشد.")
        return
        
    await callback.message.edit_text(
        f"⚠️ آیا از حذف رشته «{field['field_name']}» اطمینان دارید؟\nاین عمل غیرقابل بازگشت است.",
        reply_markup=kb_yes_no(f"fdel_{field_id}_{case_id}")
    )
    await callback.answer()

@router.callback_query(F.data.startswith("confirm_fdel_"))
async def handle_field_delete_confirm(callback: CallbackQuery, db_path: str):
    parts = callback.data.split("_")
    # confirm_fdel_{id}_{case_id}_yes/no
    field_id = parts[2]
    case_id = parts[3]
    decision = parts[4]
    
    if decision == "yes":
        db.delete_case_field(db_path, int(field_id))
        await callback.message.answer(f"✅ رشته با موفقیت حذف شد.", reply_markup=kb_cases_menu())
    else:
        await callback.message.answer("❌ عملیات لغو شد.")
    
    await callback.message.delete()
    await callback.answer()

@router.callback_query(F.data.startswith("case_status_"))
async def handle_case_status_callback(callback: CallbackQuery, state: FSMContext, db_path: str):
    case_id = callback.data.replace("case_status_", "")
    fields = db.get_case_fields(db_path, case_id)
    
    if not fields:
        # Fallback for old cases or missing fields
        await state.update_data(status_case_id=case_id)
        await state.set_state(CaseManagement.selecting_field_for_status) # We reuse this to show options
        await callback.message.answer("⚠️ این پرونده هیچ رشته‌ای ندارد. وضعیت کل پرونده را انتخاب کنید:", reply_markup=kb_status_change(case_id))
    else:
        await state.update_data(status_case_id=case_id)
        await state.set_state(CaseManagement.selecting_field_for_status)
        await callback.message.answer("🎓 لطفاً رشته مورد نظر برای تغییر وضعیت را انتخاب کنید:", reply_markup=kb_field_selection(fields, "field_status_"))
    
    await callback.answer()

@router.callback_query(CaseManagement.selecting_field_for_status, F.data.startswith("field_status_"))
async def select_field_for_status(callback: CallbackQuery, state: FSMContext):
    field_id = int(callback.data.replace("field_status_", ""))
    await state.update_data(status_field_id=field_id)
    # Important: We need to pass field_id so that the next callback knows which field to update
    await callback.message.edit_text("🎨 وضعیت جدید را انتخاب کنید:", reply_markup=kb_status_change(str(field_id)))
    await callback.answer()

@router.callback_query(F.data.startswith("status_"))
async def handle_status_selection(callback: CallbackQuery, state: FSMContext, db_path: str):
    data = callback.data.split("_")
    new_status = data[1]
    target_id = data[2] # This is field_id for new cases, case_id for legacy
    
    await state.update_data(new_status=new_status, status_target_id=target_id)
    
    if new_status == "yellow":
        await state.set_state(CaseManagement.entering_status_reason)
        await callback.message.answer("⚠️ علت وضعیت زرد را وارد کنید:")
    else:
        await process_status_update(callback.message, state, db_path, None)
    
    await callback.answer()

async def process_status_update(message: Message, state: FSMContext, db_path: str, yellow_reason: str | None):
    data = await state.get_data()
    new_status = data.get("new_status")
    field_id = data.get("status_field_id")
    case_id = data.get("status_case_id")
    
    if field_id:
        db.update_case_field_status(db_path, field_id, new_status, yellow_reason)
        field = db.get_case_field(db_path, field_id)
        field_name = field['field_name'] if field else "رشته"
        
        # Determine the case_id from the field if not in state
        if not case_id and field:
            case_id = field['case_id']

        # Notify Agency/Client about the specific field change
        if case_id:
            case_info = db.get_case(db_path, case_id)
            if case_info:
                owner_code = case_info['owner_license_code']
                users = db.get_users_by_license(db_path, owner_code)
                status_emoji = "🔴" if new_status == 'red' else "🟡" if new_status == 'yellow' else "🟢"
                notify_text = f"🔄 تغییر وضعیت در پرونده `{case_id}`\n🎓 رشته: *{field_name}*\n📍 وضعیت جدید: {status_emoji} {new_status}"
                if yellow_reason:
                    notify_text += f"\n⚠️ علت: {yellow_reason}"
                
                for u in users:
                    try:
                        await message.bot.send_message(u['user_id'], notify_text, parse_mode="Markdown")
                    except: pass

        await message.answer(f"✅ وضعیت رشته «{field_name}» با موفقیت به {new_status} تغییر یافت.", reply_markup=get_smart_kb(kb_cases_menu, message.from_user.id, db_path))
    else:
        # Legacy support
        db.update_case_status(db_path, case_id, new_status, yellow_reason)
        await message.answer(f"✅ وضعیت پرونده به {new_status} تغییر یافت.")
    
    await state.clear()

@router.message(InterviewManagement.entering_followup_notes)
async def handle_followup_notes(message: Message, state: FSMContext, cfg, db_path: str):
    data = await state.get_data()
    interview_id = data.get("interview_id")
    action = data.get("followup_action")
    notes = message.text.strip()
    result = "completed" if action == "completed" else "no_show"
    db.update_interview_followup(db_path, interview_id, result, notes)
    interview = next((i for i in db.get_interviews(db_path) if i["id"] == interview_id), None)
    if interview:
        await message.bot.send_message(
            cfg.super_admin_id,
            f"📋 گزارش مصاحبه\n\n"
            f"شرکت: {interview['company_name']}\n"
            f"وضعیت: {'✅ انجام شد' if result == 'completed' else '❌ انجام نشد'}\n"
            f"توضیحات: {notes}"
        )
    await message.answer("✅ ثبت شد! مرسی از همکاریت 🙏")
    await state.clear()


@router.callback_query(F.data.startswith("edit_iv_"))
async def edit_interview_manual(callback: CallbackQuery, state: FSMContext, db_path: str):
    iv_id = int(callback.data.replace("edit_iv_", ""))
    iv = db.get_interview(db_path, iv_id)
    if not iv:
        await callback.answer("❌ مصاحبه یافت نشد.")
        return

    # Store necessary info in state
    await state.update_data(editing_iv_id=iv_id)
    
    # Define fields to check (ordered for step-by-step editing)
    fields_to_check = [
        ("company_name", "🏢 نام شرکت"),
        ("employer_name", "👤 نام کارفرما"),
        ("city", "📍 شهر"),
        ("platform", "🌐 پلتفرم (مثلاً Zoom)"),
        ("scheduled_date", "📅 تاریخ (فرمت صحیح: 03-02-2026)"),
        ("scheduled_time", "🕒 ساعت (فرمت صحیح: 14:30)"),
        ("meeting_link", "🔗 لینک جلسه"),
        ("username", "🔑 نام کاربری (Meeting ID)"),
        ("password", "🔒 رمز عبور")
    ]
    
    # Find empty fields
    empty_fields = []
    for field_key, field_label in fields_to_check:
        val = iv.get(field_key)
        if not val or val == "-" or str(val).lower() == "null":
            empty_fields.append((field_key, field_label))
    
    if not empty_fields:
        # If no empty fields, start with the first field for general edit
        await state.update_data(remaining_fields=fields_to_check[1:], current_edit_field=fields_to_check[0][0])
        await callback.message.answer(f"✏️ لطفاً {fields_to_check[0][1]} را وارد کنید:")
    else:
        # Start editing the first empty field
        current = empty_fields[0]
        remaining = empty_fields[1:]
        await state.update_data(remaining_fields=remaining, current_edit_field=current[0])
        await callback.message.answer(f"❓ فیلد «{current[1]}» خالی است. لطفاً آن را وارد کنید:")
    
    await state.set_state(InterviewManagement.editing_field)
    await callback.answer()


@router.message(InterviewManagement.editing_field)
async def process_interview_field_edit(message: Message, state: FSMContext, db_path: str):
    if message.text == "/skip":
        await skip_interview_field_edit(message, state, db_path)
        return

    data = await state.get_data()
    iv_id = data.get("editing_iv_id")
    current_field = data.get("current_edit_field")
    remaining_fields = data.get("remaining_fields", [])
    
    new_val = message.text.strip()
    
    # Validation for date
    if current_field == "scheduled_date":
        try:
            from datetime import datetime
            datetime.strptime(new_val, "%Y-%m-%d")
            await state.update_data(temp_date=new_val)
        except ValueError:
            await message.answer("❌ فرمت تاریخ اشتباه است. لطفاً به این صورت وارد کنید: 03-02-2026")
            return

    # Validation for time
    elif current_field == "scheduled_time":
        try:
            from datetime import datetime
            datetime.strptime(new_val, "%H:%M")
            data = await state.get_data()
            temp_date = data.get("temp_date")
            if not temp_date:
                # Fallback if date wasn't set for some reason
                iv = db.get_interview(db_path, iv_id)
                if iv and iv.get("scheduled_at_iso"):
                    temp_date = iv.get("scheduled_at_iso").split('T')[0]
                else:
                    temp_date = datetime.now().strftime("%Y-%m-%d")
            
            full_dt_str = f"{temp_date} {new_val}"
            dt = datetime.strptime(full_dt_str, "%Y-%m-%d %H:%M")
            iso_val = dt.isoformat() + "Z"
            
            # Update the actual field in DB
            iv = db.get_interview(db_path, iv_id)
            if iv:
                update_data = {"scheduled_at_iso": iso_val}
                try:
                    ej = json.loads(iv.get("extracted_json", "{}"))
                    ej["scheduled_at_iso"] = iso_val
                    update_data["extracted_json"] = json.dumps(ej)
                except:
                    pass
                db.update_interview(db_path, iv_id, update_data)
        except ValueError:
            await message.answer("❌ فرمت ساعت اشتباه است. لطفاً به این صورت وارد کنید: 14:30")
            return
        
        # Skip the normal DB update for scheduled_time since we handled it above
        if remaining_fields:
            next_field, next_label = remaining_fields[0]
            await state.update_data(remaining_fields=remaining_fields[1:], current_edit_field=next_field)
            await message.answer(f"لطفاً {next_label} را وارد کنید (یا اگر نمی‌خواهید تغییر دهید /skip بزنید):")
        else:
            await show_interview_summary(message, iv_id, db_path, state)
        return

    # Update database for other fields
    iv = db.get_interview(db_path, iv_id)
    if iv and current_field != "scheduled_date": # scheduled_date is temporary until time is provided
        update_data = {current_field: new_val}
        # Also update extracted_json to keep it in sync
        try:
            ej = json.loads(iv.get("extracted_json", "{}"))
            ej[current_field] = new_val
            update_data["extracted_json"] = json.dumps(ej)
        except:
            pass
        db.update_interview(db_path, iv_id, update_data)

    if remaining_fields:
        # Move to next field
        next_field, next_label = remaining_fields[0]
        await state.update_data(remaining_fields=remaining_fields[1:], current_edit_field=next_field)
        await message.answer(f"لطفاً {next_label} را وارد کنید (یا اگر نمی‌خواهید تغییر دهید /skip بزنید):")
    else:
        # Finished all fields, show the summary again
        await show_interview_summary(message, iv_id, db_path, state)


@router.message(InterviewManagement.editing_field, F.text == "/skip")
async def skip_interview_field_edit(message: Message, state: FSMContext, db_path: str):
    data = await state.get_data()
    iv_id = data.get("editing_iv_id")
    remaining_fields = data.get("remaining_fields", [])

    if remaining_fields:
        next_field, next_label = remaining_fields[0]
        await state.update_data(remaining_fields=remaining_fields[1:], current_edit_field=next_field)
        await message.answer(f"لطفاً {next_label} را وارد کنید:")
    else:
        await show_interview_summary(message, iv_id, db_path, state)


async def show_interview_summary(message: Message, iv_id: int, db_path: str, state: FSMContext):
    iv = db.get_interview(db_path, iv_id)
    if not iv:
        await message.answer("❌ خطا در بازیابی اطلاعات.")
        await state.clear()
        return

    # Format date for display
    display_date = iv.get('scheduled_at_iso', '-')
    if display_date and 'T' in display_date:
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(display_date.replace('Z', '+00:00'))
            display_date = dt.strftime("%Y-%m-%d %H:%M")
        except:
            pass

    # Get selected field
    extracted = json.loads(iv['extracted_json']) if iv.get('extracted_json') else {}
    selected_field = extracted.get('selected_field', '')
    field_suffix = f" ({selected_field})" if selected_field else ""

    text = f"📋 اطلاعات به‌روزرسانی شده:{field_suffix}\n\n"
    text += f"🏢 شرکت: {iv.get('company_name', '-')}\n"
    text += f"👤 کارفرما: {iv.get('employer_name', '-')}\n"
    text += f"📍 شهر: {iv.get('city', '-')}\n"
    text += f"🌐 پلتفرم: {iv.get('platform', '-')}\n"
    text += f"🔑 نام کاربری (Meeting ID): {iv.get('username', '-')}\n"
    text += f"🔒 رمز عبور: {iv.get('password', '-')}\n"
    text += f"📅 تاریخ: {display_date} (به وقت آلمان)\n\n"
    text += "آیا این اطلاعات درست است؟"
    
    buttons = []
    meeting_link = iv.get('meeting_link')
    if meeting_link and meeting_link.startswith("http"):
        buttons.append([InlineKeyboardButton(text="🔗 ورود به جلسه", url=meeting_link)])
    
    buttons.extend([
        [InlineKeyboardButton(text="✅ تایید و ثبت", callback_data=f"confirm_iv_{iv_id}")],
        [InlineKeyboardButton(text="✏️ ویرایش دستی", callback_data=f"edit_iv_{iv_id}")],
        [InlineKeyboardButton(text="🔄 استخراج مجدد", callback_data=f"retry_iv_{iv_id}")],
    ])
    
    # Add delete buttons for admin/super admin (and optionally for case owner)
    user_db = db.get_user(db_path, message.from_user.id)
    if user_db and user_db.get('role') in ('super_admin', 'admin'):
        from .keyboards import kb_interview_delete_buttons
        del_kb = kb_interview_delete_buttons(iv_id, is_super_admin=(user_db.get('role') == 'super_admin'))
        # Merge keyboards: append rows
        buttons.extend(del_kb.inline_keyboard)

    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(InterviewManagement.confirming_extraction)


@router.callback_query(F.data.startswith("retry_iv_"))
async def retry_interview_extraction(callback: CallbackQuery, state: FSMContext, db_path: str):
    iv_id = int(callback.data.replace("retry_iv_", ""))
    # Fetch raw text and try again
    ivs = db.get_interviews(db_path)
    iv = next((i for i in ivs if i["id"] == iv_id), None)
    if iv:
        await callback.message.answer("🔄 در حال تلاش مجدد برای استخراج اطلاعات...")
        # Simulate re-triggering the same logic
        await process_interview_text(callback.message, state, iv["raw_email_text"], iv["case_id"], db_path)
    await callback.answer()


@router.callback_query(F.data.startswith("view_ticket_"))
async def view_ticket_callback(callback: CallbackQuery, db_path: str):
    ticket_id = int(callback.data.replace("view_ticket_", ""))
    ticket = db.get_ticket(db_path, ticket_id)
    if not ticket:
        await callback.answer("تیکت یافت نشد.")
        return
        
    messages = db.get_ticket_messages(db_path, ticket_id)
    
    header = f"🎫 *جزئیات تیکت #{ticket_id}*\n"
    header += f"📝 موضوع: {ticket['subject'] or 'بدون موضوع'}\n"
    header += f"📅 تاریخ: {ticket['created_at']}\n"
    header += f"📊 وضعیت: {'🟢 باز' if ticket['status'] == 'open' else '🔴 بسته'}\n\n"
    header += "💬 تاریخچه گفتگو:\n"
    
    full_history = ""
    for m in messages:
        role = "👤 کاربر" if m['sender_role'] not in ("admin", "super_admin") else "🛠 مدیریت"
        full_history += f"┄┄┄┄┄┄┄┄┄┄┄┄\n{role}:\n{m['text']}\n"
    
    # Send header
    await callback.message.answer(header, parse_mode="Markdown")
    
    # Send history in chunks of 4000 chars to avoid Telegram limit
    if not full_history:
        await callback.message.answer("⚠️ پیامی در این تیکت یافت نشد.")
    else:
        for i in range(0, len(full_history), 4000):
            chunk = full_history[i:i+4000]
            # Only add keyboard to the LAST chunk if it's open
            markup = None
            if i + 4000 >= len(full_history) and ticket['status'] == 'open':
                markup = kb_user_ticket_actions(ticket_id)
            
            await callback.message.answer(chunk, reply_markup=markup)
            
    await callback.answer()


@router.callback_query(F.data.startswith("user_ticket_reply_"))
async def user_ticket_reply_callback(callback: CallbackQuery, state: FSMContext):
    ticket_id = int(callback.data.replace("user_ticket_reply_", ""))
    await state.update_data(ticket_id=ticket_id)
    await state.set_state(TicketManagement.entering_reply)
    await callback.message.answer("📝 لطفاً پاسخ خود را بنویسید:")
    await callback.answer()


@router.callback_query(F.data.startswith("user_ticket_close_"))
async def user_ticket_close_callback(callback: CallbackQuery, bot: Bot, db_path: str, cfg):
    await ticket_close(callback, bot, db_path, cfg)


@router.callback_query(F.data.startswith("confirm_iv_"))
async def confirm_iv_extraction(callback: CallbackQuery, db_path: str):
    iv_id = int(callback.data.replace("confirm_iv_", ""))
    db.update_interview(db_path, iv_id, {"status": "confirmed"})
    await callback.message.edit_text("✅ مصاحبه با موفقیت تایید و در تقویم ثبت شد.")
    await callback.answer()


@router.callback_query()
async def handle_callbacks(callback: CallbackQuery, state: FSMContext, bot: Bot, cfg, db_path: str):
    data = callback.data
    print(f"[LOG] handle_callbacks received: {data}")
    await callback.answer()
    if data.startswith("case_status_"):
        case_id = data.replace("case_status_", "")
        from .keyboards import kb_status_change
        await callback.message.edit_text(f"🔄 تغییر وضعیت پرونده {case_id}\n\nوضعیت جدید را انتخاب کنید:", reply_markup=kb_status_change(case_id))

    elif data.startswith("status_"):
        parts = data.split("_")
        status = parts[1]
        case_id = parts[2]
        if status == "yellow":
            await callback.message.answer("⚠️ دلیل وضعیت زرد را وارد کنید:")
            await state.update_data(case_id_for_status=case_id, target_status="yellow")
            await state.set_state(CaseManagement.entering_status_reason)
        else:
            db.update_case_status(db_path, case_id, status)
            status_display = get_status_display(status)
            await callback.message.edit_text(f"✅ وضعیت پرونده {case_id} با موفقیت به {status_display} تغییر یافت.")
            
            # Notify Agency/Client
            case = db.get_case(db_path, case_id)
            if case:
                members = db.get_users_by_license(db_path, case['owner_license_code'])
                notify_text = f"🔄 وضعیت پرونده {case_id} به {status_display} تغییر یافت."
                for m in members:
                    try:
                        await bot.send_message(m['user_id'], notify_text)
                    except: pass


    elif data.startswith("case_msg_"):
        case_id = data.replace("case_msg_", "")
        case = db.get_case(db_path, case_id)
        if not case:
            await callback.answer("❌ پرونده یافت نشد.")
            return
        await state.update_data(target_license=case['owner_license_code'], msg_type="targeted")
        await state.set_state(MessageManagement.entering_message_text)
        await callback.message.edit_text(f"📝 پیام خود را برای صاحب پرونده {case_id} بنویسید:")

    elif data.startswith("case_end_"):
        case_id = data.replace("case_end_", "")
        await callback.message.edit_text(f"⚠️ آیا از پایان دادن به پرونده {case_id} اطمینان دارید؟", reply_markup=kb_yes_no(f"case_end_{case_id}"))

    elif data.startswith("confirm_case_end_"):
        await callback.answer()
        case_id = data.replace("confirm_case_end_", "").replace("_yes", "").replace("_no", "")
        if "_no" in data:
            await callback.message.edit_text("❌ عملیات لغو شد.")
            return
        db.update_case_status(db_path, case_id, "archived")
        await callback.message.answer(f"✅ پرونده {case_id} با موفقیت به پایان رسید.", reply_markup=get_smart_kb(kb_cases_menu, callback.from_user.id, db_path))
        await callback.message.delete()

    elif data.startswith("case_comment_"):
        case_id = data.replace("case_comment_", "")
        await state.update_data(case_id_for_comment=case_id)
        await state.set_state(CaseManagement.entering_case_comment)
        await callback.message.answer(f"📝 لطفا کامنت خود را برای پرونده {case_id} وارد کنید:")

    elif data.startswith("comment_visibility_"):
        parts = data.split("_")
        is_private = int(parts[2])
        case_id = parts[3]
        
        state_data = await state.get_data()
        comment_text = state_data.get("pending_comment")
        file_id = state_data.get("pending_file_id")
        
        if not comment_text and not file_id:
            await callback.message.edit_text("❌ خطا در ثبت کامنت. دوباره تلاش کنید.")
            return

        comment_id = db.add_case_comment(db_path, case_id, callback.from_user.id, comment_text, is_private, file_id)
        
        success_msg = "✅ کامنت با موفقیت ثبت شد."
        if is_private == 0:
            case = db.get_case(db_path, case_id)
            if case:
                members = db.get_users_by_license(db_path, case['owner_license_code'])
                notify_text = f"🔔 پیام جدید از مدیریت برای پرونده {case_id}:\n\n{comment_text}"
                
                from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
                read_kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="✅ متوجه شدم (تایید خواندن)", callback_data=f"read_comment_{comment_id}")]
                ])

                for m in members:
                    try:
                        if file_id:
                            await bot.send_document(m['user_id'], file_id, caption=notify_text, parse_mode="Markdown", reply_markup=read_kb)
                        else:
                            await bot.send_message(m['user_id'], notify_text, parse_mode="Markdown", reply_markup=read_kb)
                    except: pass
                success_msg += "\n📢 اطلاع‌رسانی به موسسه/کلاینت انجام شد."

        await callback.message.edit_text(success_msg)
        await state.clear()

    elif data.startswith("case_contract_edit_"):
        case_id = data.replace("case_contract_edit_", "")
        await state.update_data(contract_case_id=case_id)
        await state.set_state(CaseManagement.waiting_for_contract_edit)
        await callback.message.answer(f"📄 لطفاً فایل PDF جدید قرارداد برای پرونده {case_id} را ارسال کنید.\n\n(در صورت انصراف، این پیام را نادیده بگیرید یا پیام دیگری بفرستید)", reply_markup=kb_back_main())
        await callback.answer()

    elif data.startswith("case_contract_"):
        case_id = data.replace("case_contract_", "")
        case = db.get_case(db_path, case_id)
        if not case:
            await callback.answer("❌ پرونده یافت نشد.", show_alert=True)
            return

        file_id = case.get("contract_file_id")
        user = db.get_user(db_path, callback.from_user.id)
        is_admin = user["role"] in ("admin", "super_admin") if user else False

        if file_id:
            await bot.send_document(callback.from_user.id, file_id, caption=f"📄 قرارداد پرونده {case_id}")
            await callback.answer("✅ قرارداد ارسال شد.")
        elif is_admin:
            await state.update_data(contract_case_id=case_id)
            await state.set_state(CaseManagement.waiting_for_contract)
            await callback.message.answer(f"📥 هنوز قراردادی برای پرونده {case_id} آپلود نشده است.\n\nلطفاً فایل PDF قرارداد را ارسال کنید:")
            await callback.answer()
        else:
            await callback.answer("⚠️ قراردادی برای این پرونده موجود نیست.", show_alert=True)

    elif data.startswith("read_comment_"):
        comment_id = int(data.replace("read_comment_", ""))
        comment = db.set_comment_read(db_path, comment_id)
        if comment:
            await callback.message.edit_reply_markup(reply_markup=None)
            await callback.answer("✅ تایید خواندن ثبت شد.")
            # Notify Super Admin
            all_users = db.get_all_admin_users(db_path)
            super_admins = [u for u in all_users if u['role'] == 'super_admin']
            user_who_read = db.get_user(db_path, callback.from_user.id)
            name = user_who_read['full_name'] if user_who_read else "کاربر"
            notify_admin = f"👁️ کامنت پرونده {comment['case_id']} توسط {name} خوانده شد.\n\nمتن: {comment['comment_text'][:50]}..."
            for admin in super_admins:
                try:
                    await bot.send_message(admin['user_id'], notify_admin)
                except: pass

    elif data.startswith("case_docs_"):
        case_id = data.replace("case_docs_", "")
        docs = db.get_case_documents(db_path, case_id)
        if not docs:
            await callback.message.answer(f"📁 پرونده {case_id} هیچ مدرک آپلود شده‌ای ندارد.")
        else:
            text = f"📄 مدارک پرونده {case_id}:\n\n"
            for d in docs:
                status_icon = "⏳" if d['status'] == 'pending' else "✅" if d['status'] == 'approved' else "❌"
                text += f"{status_icon} {d['doc_type']} | وضعیت: {d['status']}\n"
            await callback.message.answer(text)
        
        user = db.get_user(db_path, callback.from_user.id)
        if user['role'] in ('agency', 'direct_client'):
            await callback.message.answer("آیا می‌خواهید مدارک جدید اضافه کنید؟", reply_markup=kb_yes_no(f"start_docs_{case_id}"))

    elif data.startswith("confirm_start_docs_"):
        if "_yes" in data:
            case_id = data.replace("confirm_start_docs_", "").replace("_yes", "")
            await state.update_data(doc_case_id=case_id, doc_index=0)
            db.create_document_request(db_path, case_id)
            await show_next_doc_request(callback.message, state, case_id, db_path)
        else:
            await callback.message.answer("لغو شد.")

    elif data.startswith("doc_next_"):
        await callback.message.delete()
        await show_next_review_doc(callback.message, state, db_path)

    elif data.startswith("doc_approve_all_"):
        case_id = data.replace("doc_approve_all_", "")
        db.approve_document_request(db_path, case_id, callback.from_user.id)
        
        # GDrive Upload for all approved docs in this case
        await callback.message.answer(f"⏳ در حال آپلود مدارک پرونده {case_id} به گوگل درایو...")
        try:
            docs = db.get_case_documents(db_path, case_id)
            approved_docs = [d for d in docs if d['status'] == 'approved']
            
            if approved_docs:
                case = db.get_case(db_path, case_id)
                lic = db.get_license(db_path, case['owner_license_code'])
                institution_name = lic.agency_name if lic and lic.agency_name else (lic.code if lic else "Unknown")
                case_name = f"{case['client_name']} ({case['case_id']})"
                
                gdrive = GDriveService(
                    credentials_path=r"C:\Users\Kasra\Desktop\bot\gdrive_credentials.json",
                    token_path=r"C:\Users\Kasra\Desktop\bot\gdrive_token.json"
                )
                
                # Root Folders
                parent_root_id = "16v72-SR6iAb9YsS2is4B8RyzC3CfbDcn"
                root_folder_name = "موسسات" if case['owner_type'] == 'agency' else "کلاینت ها"
                root_folder_id = gdrive.get_or_create_folder(root_folder_name, parent_id=parent_root_id)
                
                # Institution/Client Folder
                institution_name = lic.agency_name if lic and lic.agency_name else (lic.code if lic else "Unknown")
                parent_folder_id = gdrive.get_or_create_folder(institution_name, parent_id=root_folder_id)
                
                # Case Folder
                case_name = f"{case['client_name']} ({case['case_id']})"
                case_folder_id = gdrive.get_or_create_folder(case_name, parent_id=parent_folder_id)
                
                success_count = 0
                duplicate_count = 0
                for doc in approved_docs:
                    # Skip if no file_id (skipped document)
                    if not doc.get('file_id'):
                        continue
                        
                    doc_type = doc['doc_type']
                    german_name = DOC_TYPE_MAPPING.get(doc_type)
                    
                    if german_name:
                        extension = ".pdf" if (doc['file_name'] or "").lower().endswith('.pdf') else ".jpg"
                        final_file_name = f"{german_name}{extension}"
                    else:
                        final_file_name = doc['file_name'] or f"{doc['doc_type']}.jpg"
                    
                    # Check for duplicate
                    existing_files = gdrive.find_file(final_file_name, case_folder_id)
                    if existing_files:
                        duplicate_count += 1
                        continue

                    try:
                        file = await bot.get_file(doc['file_id'])
                        file_content = await bot.download_file(file.file_path)
                        content_bytes = file_content.read()
                        
                        mime_type = "application/pdf" if final_file_name.lower().endswith('.pdf') else "image/jpeg"
                        await gdrive.upload_file(
                            file_content=content_bytes,
                            file_name=final_file_name,
                            folder_id=case_folder_id,
                            mime_type=mime_type
                        )
                        success_count += 1
                    except Exception as e:
                        print(f"[GDrive Multi-Upload Error] {doc['doc_type']}: {e}")

                msg_parts = []
                if success_count > 0:
                    msg_parts.append(f"✅ تعداد {success_count} مدرک جدید با موفقیت ذخیره شد.")
                if duplicate_count > 0:
                    msg_parts.append(f"⚠️ تعداد {duplicate_count} فایل از قبل در درایو موجود بود و نادیده گرفته شد.")
                
                if msg_parts:
                    await callback.message.answer("\n".join(msg_parts))
        except Exception as e:
            await callback.message.answer(f"⚠️ خطا در فرآیند آپلود دسته‌جمعی: {str(e)}")

        await callback.message.answer(f"✅ تمام مدارک پرونده {case_id} تایید شدند.")

    elif data.startswith("doc_reject_"):
        doc_id = int(data.replace("doc_reject_", ""))
        await callback.message.answer("💬 دلیل رد کردن این مدرک را بنویسید:")
        await state.update_data(reject_doc_id=doc_id)
        await state.set_state(DocumentReview.entering_rejection_reason)
    elif data.startswith("lic_cap_"):
        code = data.replace("lic_cap_", "")
        await state.update_data(selected_license=code)
        await state.set_state(LicenseManagement.entering_new_capacity)
        await callback.message.answer(f"ظرفیت جدید لایسنس {code} را وارد کنید:")
    elif data.startswith("lic_deact_"):
        print(f"[LOG] lic_deact_ called with data: {data}")
        await callback.answer()
        code = data.replace("lic_deact_", "")
        await callback.message.answer(f"آیا لایسنس {code} غیرفعال شود؟", reply_markup=kb_yes_no(f"lic_deact_{code}"))
    elif data.startswith("lic_members_"):
        code = data.replace("lic_members_", "")
        users = db.get_users_by_license(db_path, code)
        if users:
            text = f"اعضای لایسنس {code}:\n\n"
            for u in users:
                text += f"- {u['full_name']} ({u['role']})\n"
            await callback.message.answer(text)
        else:
            await callback.message.answer("هیچ عضوی ندارد.")
    elif data.startswith("lic_kick_"):
        print(f"[LOG] lic_kick_ handled in catch-all: {data}")
        code = data.replace("lic_kick_", "")
        members = db.get_license_members(db_path, code)
        if not members:
            await callback.message.answer("هیچ عضوی ندارد.")
            return
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
        buttons = []
        for m in members:
            name = m['full_name'] or f"آیدی: {m['user_id']}"
            buttons.append([InlineKeyboardButton(text=f"❌ حذف {name}", callback_data=f"kick_user_{m['user_id']}_{code}")])
        await callback.message.answer(f"👥 اعضای لایسنس {code}:\nکاربری که می‌خواهید حذف کنید را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    elif data.startswith("kick_user_"):
        print(f"[LOG] kick_user_ handled in catch-all: {data}")
        parts = data.replace("kick_user_", "").split("_")
        user_id = int(parts[0])
        code = parts[1]
        db.kick_user_from_license(db_path, user_id)
        await callback.message.answer(f"✅ کاربر {user_id} از لایسنس {code} حذف شد.", reply_markup=kb_licenses_menu())
    elif data.startswith("admin_remove_"):
        user_id = int(data.replace("admin_remove_", ""))
        with db.connect(db_path) as conn:
            conn.execute("UPDATE users SET role = 'direct_client' WHERE user_id = ?", (user_id,))
            conn.execute("DELETE FROM admin_permissions WHERE user_id = ?", (user_id,))
        await callback.message.answer(f"✅ ادمین {user_id} با موفقیت حذف شد.", reply_markup=kb_admins_menu())
    elif data.startswith("admin_perms_"):
        user_id = int(data.replace("admin_perms_", ""))
        perms = db.get_admin_permissions(db_path, user_id)
        if not perms:
            await callback.message.answer("⚠️ این کاربر در جدول دسترسی‌ها ثبت نشده. ابتدا او را به عنوان ادمین اضافه کنید.")
            return
        from .keyboards import kb_admin_permissions
        user = db.get_user(db_path, user_id)
        name = (user.get('full_name') or str(user_id)) if user else str(user_id)
        await callback.message.answer(
            f"🔐 دسترسی‌های *{name}*\nبرای روشن/خاموش کردن هر دسترسی کلیک کنید:",
            reply_markup=kb_admin_permissions(user_id, perms),
            parse_mode="Markdown"
        )
    elif data.startswith("admin_makesup_"):
        user_id = int(data.replace("admin_makesup_", ""))
        with db.connect(db_path) as conn:
            conn.execute("UPDATE users SET role = 'super_admin' WHERE user_id = ?", (user_id,))
        user = db.get_user(db_path, user_id)
        name = (user.get('full_name') or str(user_id)) if user else str(user_id)
        await callback.message.answer(f"✅ *{name}* اکنون سوپرادمین شد! ⭐", reply_markup=kb_admins_menu(), parse_mode="Markdown")
    elif data.startswith("toggle_perm_"):
        perm_data = data.replace("toggle_perm_", "")
        parts = perm_data.split("_", 1)
        user_id = int(parts[0])
        perm_key = parts[1]
        perms = db.get_admin_permissions(db_path, user_id)
        if not perms:
            await callback.message.answer("ادمین یافت نشد.")
            return
        current_val = perms.get(perm_key, 0)
        new_val = 0 if current_val else 1
        with db.connect(db_path) as conn:
            conn.execute(f"UPDATE admin_permissions SET {perm_key} = ? WHERE user_id = ?", (new_val, user_id))
        new_perms = db.get_admin_permissions(db_path, user_id)
        from .keyboards import kb_admin_permissions
        await callback.message.edit_reply_markup(reply_markup=kb_admin_permissions(user_id, new_perms))


async def send_scheduled_msg_task(bot: Bot, db_path: str, target_code: str, text: str):
    print(f"[LOG] Executing scheduled task for {target_code}")
    members = db.get_users_by_license(db_path, target_code)
    if not members:
        print(f"[LOG] No members found for license {target_code}")
        return
    
    sent = 0
    for m in members:
        try:
            await bot.send_message(m["user_id"], f"⏰ *پیام زمان‌بندی شده از مدیریت*\n\n{text}", parse_mode="Markdown")
            sent += 1
        except Exception as e:
            print(f"[LOG] Failed to send message to {m['user_id']}: {e}")
    
    print(f"[LOG] Scheduled task finished. Sent to {sent}/{len(members)} members.")

@router.message(CaseManagement.waiting_for_contract)
@router.message(CaseManagement.waiting_for_contract_edit)
async def handle_contract_upload(message: Message, state: FSMContext, db_path: str):
    if not message.document or not message.document.file_name.lower().endswith(".pdf"):
        await message.answer("❌ خطا: فقط فایل با فرمت PDF پذیرفته می‌شود. لطفاً فایل قرارداد را به صورت PDF ارسال کنید.")
        return

    data = await state.get_data()
    case_id = data.get("contract_case_id")
    if not case_id:
        await message.answer("❌ خطای سیستمی: پرونده مشخص نیست. مجدداً تلاش کنید.")
        await state.clear()
        return

    file_id = message.document.file_id
    db.update_case_contract(db_path, case_id, file_id)

    current_state = await state.get_state()
    action_text = "آپلود" if current_state == CaseManagement.waiting_for_contract else "ویرایش"
    
    await message.answer(f"✅ قرارداد پرونده {case_id} با موفقیت {action_text} شد.")
    await message.bot.send_document(message.from_user.id, file_id, caption=f"📄 فایل نهایی قرارداد پرونده {case_id}")
    await state.clear()


@router.message(MessageManagement.entering_schedule_time)
async def enter_schedule_time(message: Message, state: FSMContext, bot: Bot, db_path: str, scheduler: "AsyncIOScheduler"):
    date_str = message.text.strip()
    try:
        from datetime import datetime
        
        # Get scheduler timezone
        tz = scheduler.timezone
        
        # Parse user input as naive
        naive_run_date = datetime.strptime(date_str, "%Y-%m-%d %H:%M")
        
        # Localize it compatibly (works for both pytz and zoneinfo)
        if hasattr(tz, 'localize'):
            run_date = tz.localize(naive_run_date)
        else:
            run_date = naive_run_date.replace(tzinfo=tz)
        
        # Get current time in same timezone
        now = datetime.now(tz)
        
        if run_date <= now:
            await message.answer("❌ زمان انتخابی باید در آینده باشد. دوباره تلاش کنید:")
            return
            
        data = await state.get_data()
        target_code = data.get("sched_target_code")
        text = data.get("sched_text")
        
        # Schedule the job
        scheduler.add_job(
            send_scheduled_msg_task,
            "date",
            run_date=run_date,
            args=[bot, db_path, target_code, text]
        )
        
        await message.answer(
            f"✅ پیام شما با موفقیت زمان‌بندی شد\n\n"
            f"📅 تاریخ: `{date_str}`\n"
            f"🎯 گیرنده: `{target_code}`\n"
            f"⏰ ساعت فعلی سیستم: `{now.strftime('%H:%M:%S')}`",
            parse_mode="Markdown",
            reply_markup=get_smart_kb(kb_send_message_menu, message.from_user.id, db_path)
        )
        await state.clear()
        
    except ValueError:
        await message.answer("❌ فرمت تاریخ اشتباه است. لطفاً طبق مثال وارد کنید:\n`2024-03-25 14:30`", parse_mode="Markdown")
    except Exception as e:
        import traceback
        print(f"[ERROR] Scheduling failed: {e}")
        traceback.print_exc()
        await message.answer(f"❌ خطایی در زمان‌بندی رخ داد:\n`{str(e)}`", parse_mode="Markdown")


@router.callback_query(F.data == "view_my_tickets")
async def view_my_tickets_callback(callback: CallbackQuery, db_path: str):
    user_id = callback.from_user.id
    tickets = db.get_all_tickets(db_path, user_id=user_id)
    if not tickets:
        await callback.message.answer("🎫 شما هیچ تیکت فعالی ندارید.")
    else:
        text = "🎫 لیست تیکت‌های شما:\n\n"
        for t in tickets:
            status = "🟢 باز" if t['status'] == 'open' else "🔴 بسته"
            text += f"#{t['id']} | {t['subject'] or 'بدون موضوع'} | وضعیت: {status}\n"
        await callback.message.answer(text)
    await callback.answer()