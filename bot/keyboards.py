from aiogram.types import KeyboardButton, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup


def kb_request_contact() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="ارسال شماره موبایل", request_contact=True)]],
        resize_keyboard=True,
        selective=True,
    )


def kb_admin_main(role: str = "super_admin", perms: dict = None) -> ReplyKeyboardMarkup:
    if role == "super_admin":
        buttons = [
            [KeyboardButton(text="📊 آمار"), KeyboardButton(text="📁 پرونده‌ها")],
            [KeyboardButton(text="🔑 لایسنس‌ها"), KeyboardButton(text="🎫 تیکت‌ها")],
            [KeyboardButton(text="📅 مصاحبه‌های جدید"), KeyboardButton(text="💬 ارسال پیام")],
            [KeyboardButton(text="💰 یادآوری اقساط")],
            [KeyboardButton(text="👥 ادمین‌ها"), KeyboardButton(text="📱 تست پیامک")],
            [KeyboardButton(text="⚙️ ریست فکتوری")],
        ]
    else:
        # ادمین معمولی - دکمه‌ها بر اساس دسترسی
        perms = perms or {}
        buttons = []
        
        # ردیف اول: پرونده‌ها
        row1 = []
        if perms.get("can_manage_cases") or perms.get("can_change_status"):
            row1.append(KeyboardButton(text="📁 پرونده‌ها"))
        if row1: buttons.append(row1)
        
        # ردیف دوم: لایسنس‌ها و تیکت‌ها
        row2 = []
        if perms.get("can_manage_licenses"):
            row2.append(KeyboardButton(text="🔑 لایسنس‌ها"))
        if perms.get("can_manage_tickets") or perms.get("can_reply_tickets"):
            row2.append(KeyboardButton(text="🎫 تیکت‌ها"))
        if row2: buttons.append(row2)
        
        # ردیف سوم: مصاحبه‌ها و ارسال پیام
        row3 = []
        if perms.get("can_manage_interviews"):
            row3.append(KeyboardButton(text="📅 مصاحبه‌های جدید"))
        if perms.get("can_send_messages") or perms.get("can_broadcast"):
            row3.append(KeyboardButton(text="💬 ارسال پیام"))
        if row3: buttons.append(row3)
        
        # ردیف چهارم: ادمین‌ها و تست پیامک (معمولاً برای ادمین عادی نیست ولی اگر دسترسی داشت)
        row4 = []
        if perms.get("can_manage_admins"):
            row4.append(KeyboardButton(text="👥 ادمین‌ها"))
        if row4: buttons.append(row4)

    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


def kb_back_main() -> ReplyKeyboardMarkup:
    buttons = [[KeyboardButton(text="بازگشت به مرحله قبل"), KeyboardButton(text="منوی اصلی")]]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


def kb_agency_main() -> ReplyKeyboardMarkup:
    buttons = [
        [KeyboardButton(text="📁 پرونده‌های موسسه")],
        [KeyboardButton(text="🎫 تیکت‌ها")],
        [KeyboardButton(text="📅 مصاحبه‌ها")],
        [KeyboardButton(text="💬 پیام‌ها")],
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


def kb_direct_client_main() -> ReplyKeyboardMarkup:
    buttons = [
        [KeyboardButton(text="📋 پرونده من")],
        [KeyboardButton(text="🎫 تیکت‌ها")],
        [KeyboardButton(text="📅 مصاحبه‌ها")],
        [KeyboardButton(text="💬 پیام‌ها")],
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


def kb_licenses_menu(role: str = "super_admin", perms: dict = None) -> ReplyKeyboardMarkup:
    if role == "super_admin":
        buttons = [
            [KeyboardButton(text="➕ ساخت لایسنس موسسه"), KeyboardButton(text="➕ ساخت لایسنس کلاینت")],
            [KeyboardButton(text="➕ ساخت لایسنس بلاگر"), KeyboardButton(text="📋 اطلاعات کاربران")],
            [KeyboardButton(text="👁 لایسنس‌های موسسات"), KeyboardButton(text="👁 لایسنس‌های کلاینت‌ها")],
            [KeyboardButton(text="👁 لایسنس‌های بلاگرها"), KeyboardButton(text="📈 افزایش ظرفیت")],
            [KeyboardButton(text="🔄 غیرفعال/فعال کردن"), KeyboardButton(text="🗑 حذف لایسنس")],
            [KeyboardButton(text="👥 مشاهده اعضا"), KeyboardButton(text="🚫اخراج کاربر")],
            [KeyboardButton(text="🏠 منوی اصلی")],
        ]
    else:
        perms = perms or {}
        buttons = []
        if perms.get("can_manage_licenses"):
            buttons.append([KeyboardButton(text="➕ ساخت لایسنس موسسه"), KeyboardButton(text="➕ ساخت لایسنس کلاینت")])
            buttons.append([KeyboardButton(text="➕ ساخت لایسنس بلاگر"), KeyboardButton(text="👁 لایسنس‌های موسسات")])
            buttons.append([KeyboardButton(text="👁 لایسنس‌های کلاینت‌ها"), KeyboardButton(text="👁 لایسنس‌های بلاگرها")])
            buttons.append([KeyboardButton(text="📈 افزایش ظرفیت"), KeyboardButton(text="🔄 غیرفعال/فعال کردن")])
            buttons.append([KeyboardButton(text="👥 مشاهده اعضا"), KeyboardButton(text="🚫اخراج کاربر")])
        else:
            buttons.append([KeyboardButton(text="👁 لایسنس‌های موسسات"), KeyboardButton(text="👁 لایسنس‌های کلاینت‌ها")])
            buttons.append([KeyboardButton(text="👁 لایسنس‌های بلاگرها")])
        buttons.append([KeyboardButton(text="🏠 منوی اصلی")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


def kb_cases_menu(role: str = "super_admin", perms: dict = None) -> ReplyKeyboardMarkup:
    if role == "super_admin":
        buttons = [
            [KeyboardButton(text="➕ اضافه کردن پرونده"), KeyboardButton(text="👁 مشاهده پرونده‌ها")],
            [KeyboardButton(text="✏️ ویرایش پرونده"), KeyboardButton(text="🗑 حذف پرونده")],
            [KeyboardButton(text="📦 آرشیو پرونده‌ها")],
            [KeyboardButton(text="🏠 منوی اصلی")],
        ]
    else:
        perms = perms or {}
        buttons = []
        row1 = []
        if perms.get("can_manage_cases"):
            row1.append(KeyboardButton(text="➕ اضافه کردن پرونده"))
        row1.append(KeyboardButton(text="👁 مشاهده پرونده‌ها"))
        buttons.append(row1)
        
        if perms.get("can_manage_cases"):
            buttons.append([KeyboardButton(text="✏️ ویرایش پرونده"), KeyboardButton(text="🗑 حذف پرونده")])
            buttons.append([KeyboardButton(text="📦 آرشیو پرونده‌ها")])
            
        buttons.append([KeyboardButton(text="🏠 منوی اصلی")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


def kb_cases_owner_type() -> ReplyKeyboardMarkup:
    buttons = [
        [KeyboardButton(text="برای موسسه"), KeyboardButton(text="برای کلاینت"), KeyboardButton(text="برای بلاگر")],
        [KeyboardButton(text="منوی اصلی")],
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


def kb_interview_owner_type() -> ReplyKeyboardMarkup:
    buttons = [
        [KeyboardButton(text="موسسات"), KeyboardButton(text="کلاینت ها"), KeyboardButton(text="بلاگر ها")],
        [KeyboardButton(text="منوی اصلی")],
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


def kb_tickets_menu(role: str = "super_admin", perms: dict = None) -> ReplyKeyboardMarkup:
    if role == "super_admin":
        buttons = [
            [KeyboardButton(text="🔓 تیکت‌های باز"), KeyboardButton(text="📦 آرشیو تیکت‌ها")],
            [KeyboardButton(text="🏠 منوی اصلی")],
        ]
    else:
        perms = perms or {}
        buttons = []
        row = []
        if perms.get("can_manage_tickets"):
            row.append(KeyboardButton(text="🔓 تیکت‌های باز"))
        row.append(KeyboardButton(text="📦 آرشیو تیکت‌ها"))
        buttons.append(row)
        buttons.append([KeyboardButton(text="🏠 منوی اصلی")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


def kb_interviews_menu(role: str = "super_admin", perms: dict = None) -> ReplyKeyboardMarkup:
    if role == "super_admin":
        buttons = [
            [KeyboardButton(text="➕ ثبت مصاحبه جدید"), KeyboardButton(text="👁 مشاهده مصاحبه‌ها")],
            [KeyboardButton(text="📆 مصاحبه‌های ۱۰ روز آینده")],
            [KeyboardButton(text="🗑 حذف مصاحبه")],
            [KeyboardButton(text="🏠 منوی اصلی")],
        ]
    else:
        perms = perms or {}
        buttons = []
        row = []
        if perms.get("can_manage_interviews"):
            row.append(KeyboardButton(text="➕ ثبت مصاحبه جدید"))
        row.append(KeyboardButton(text="👁 مشاهده مصاحبه‌ها"))
        buttons.append(row)
        buttons.append([KeyboardButton(text="📆 مصاحبه‌های ۱۰ روز آینده")])
        if perms.get("can_manage_interviews"):
            buttons.append([KeyboardButton(text="🗑 حذف مصاحبه")])
        buttons.append([KeyboardButton(text="🏠 منوی اصلی")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


def kb_send_message_menu(role: str = "super_admin", perms: dict = None) -> ReplyKeyboardMarkup:
    if role == "super_admin":
        buttons = [
            [KeyboardButton(text="🏢 ارسال به موسسه"), KeyboardButton(text="👤 ارسال به کلاینت")],
            [KeyboardButton(text="🤳 ارسال به بلاگر")],
            [KeyboardButton(text="📋 ارسال بر اساس پرونده"), KeyboardButton(text="📢 ارسال همگانی")],
            [KeyboardButton(text="⏰ پیام زمان‌بندی شده")],
            [KeyboardButton(text="🏠 منوی اصلی")],
        ]
    else:
        perms = perms or {}
        buttons = []
        if perms.get("can_send_messages"):
            buttons.append([KeyboardButton(text="🏢 ارسال به موسسه"), KeyboardButton(text="👤 ارسال به کلاینت")])
            buttons.append([KeyboardButton(text="🤳 ارسال به بلاگر"), KeyboardButton(text="📋 ارسال بر اساس پرونده")])
        if perms.get("can_broadcast"):
            buttons.append([KeyboardButton(text="📢 ارسال همگانی"), KeyboardButton(text="⏰ پیام زمان‌بندی شده")])
        buttons.append([KeyboardButton(text="🏠 منوی اصلی")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


def kb_admins_menu(role: str = "super_admin", perms: dict = None) -> ReplyKeyboardMarkup:
    if role == "super_admin":
        buttons = [
            [KeyboardButton(text="➕ افزودن ادمین"), KeyboardButton(text="🗑 حذف ادمین")],
            [KeyboardButton(text="🔐 مدیریت دسترسی‌ها"), KeyboardButton(text="⭐ سوپرادمین کردن")],
            [KeyboardButton(text="👁 مشاهده ادمین‌ها")],
            [KeyboardButton(text="🏠 منوی اصلی")],
        ]
    else:
        perms = perms or {}
        buttons = []
        if perms.get("can_manage_admins"):
            buttons.append([KeyboardButton(text="➕ افزودن ادمین"), KeyboardButton(text="🗑 حذف ادمین")])
            buttons.append([KeyboardButton(text="🔐 مدیریت دسترسی‌ها"), KeyboardButton(text="⭐ سوپرادمین کردن")])
        buttons.append([KeyboardButton(text="👁 مشاهده ادمین‌ها")])
        buttons.append([KeyboardButton(text="🏠 منوی اصلی")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


def kb_admin_permissions(user_id: int, perms: dict) -> InlineKeyboardMarkup:
    perm_names = {
        "can_manage_licenses": "لایسنس",
        "can_manage_cases": "پرونده",
        "can_change_status": "وضعیت",
        "can_view_phones": "شماره",
        "can_manage_tickets": "تیکت",
        "can_reply_tickets": "پاسخ تیکت",
        "can_send_messages": "پیام",
        "can_broadcast": "همگانی",
        "can_manage_interviews": "مصاحبه",
        "can_manage_admins": "ادمین",
    }
    buttons = []
    current_row = []
    for key, name in perm_names.items():
        status = "✅" if perms.get(key) else "❌"
        current_row.append(InlineKeyboardButton(text=f"{status} {name}", callback_data=f"toggle_perm_{user_id}_{key}"))
        if len(current_row) == 2:
            buttons.append(current_row)
            current_row = []
    if current_row:
        buttons.append(current_row)
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def kb_case_detail(case_id: str, is_admin: bool = True, is_active: bool = True, is_super_admin: bool = False, has_employer_contract: bool = False, has_pre_approval: bool = False) -> InlineKeyboardMarkup:
    buttons = []
    
    if is_admin:
        if is_active:
            buttons.append([
                InlineKeyboardButton(text="✏️ ویرایش", callback_data=f"case_edit_{case_id}"),
                InlineKeyboardButton(text="🔄 تغییر وضعیت", callback_data=f"case_status_{case_id}")
            ])
            buttons.append([
                InlineKeyboardButton(text="🎓 مدیریت رشته‌ها", callback_data=f"case_fields_mgmt_{case_id}"),
                InlineKeyboardButton(text="💰 مدیریت اقساط", callback_data=f"case_inst_{case_id}")
            ])
            
            # New row for employer contract and pre-approval (Admin only)
            row_files = []
            row_files.append(InlineKeyboardButton(text="📄 قرارداد کارفرما", callback_data=f"case_empl_contract_{case_id}"))
            row_files.append(InlineKeyboardButton(text="📜 پیش‌تاییدیه", callback_data=f"case_pre_appr_{case_id}"))
            buttons.append(row_files)

            buttons.append([
                InlineKeyboardButton(text="🏁 پایان پرونده", callback_data=f"case_end_{case_id}"),
                InlineKeyboardButton(text="💬 ارسال پیام", callback_data=f"case_msg_{case_id}")
            ])
            if is_super_admin:
                buttons.append([
                    InlineKeyboardButton(text="💬 ثبت کامنت (ویژه)", callback_data=f"case_comment_{case_id}")
                ])
        else:
            buttons.append([
                InlineKeyboardButton(text="💰 مدیریت اقساط", callback_data=f"case_inst_{case_id}")
            ])
            
        buttons.append([
            InlineKeyboardButton(text="📜 تاریخچه مصاحبه‌ها", callback_data=f"case_iv_history_{case_id}")
        ])
    
    # Documents row
    doc_row = [InlineKeyboardButton(text="📄 مدارک", callback_data=f"case_docs_{case_id}")]
    doc_row.append(InlineKeyboardButton(text="📝 قرارداد اصلی", callback_data=f"case_contract_{case_id}"))
    buttons.append(doc_row)

    # Show new files to everyone if they exist
    if has_employer_contract or has_pre_approval:
        row_view = []
        if has_employer_contract:
            row_view.append(InlineKeyboardButton(text="📄 مشاهده قرارداد کارفرما", callback_data=f"view_empl_contract_{case_id}"))
        if has_pre_approval:
            row_view.append(InlineKeyboardButton(text="📜 مشاهده پیش‌تاییدیه", callback_data=f"view_pre_appr_{case_id}"))
        buttons.append(row_view)

    if is_admin:
        buttons.append([
            InlineKeyboardButton(text="🗑️ حذف", callback_data=f"case_delete_{case_id}"),
            InlineKeyboardButton(text="✏️ ویرایش قرارداد اصلی", callback_data=f"case_contract_edit_{case_id}")
        ])
    else:
        # For Agency/Client
        row = [InlineKeyboardButton(text="📜 تاریخچه مصاحبه‌ها", callback_data=f"case_iv_history_{case_id}")]
        # Already added doc_row above
        buttons.append(row)
        
    buttons.append([InlineKeyboardButton(text="🔙 بازگشت به لیست", callback_data="back_to_cases_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def kb_case_selection(cases: list, prefix: str = "case_view_", page: int = 1, total_pages: int = 1) -> InlineKeyboardMarkup:
    buttons = []
    for c in cases:
        buttons.append([InlineKeyboardButton(text=f"📋 {c['case_id']} | {c['client_name']}", callback_data=f"{prefix}{c['case_id']}")])
    
    # Pagination buttons
    nav_buttons = []
    # Adjust callback_data for pagination based on prefix
    page_prefix = "cases_page_" if prefix == "case_view_" else f"{prefix}page_"
    
    if page > 1:
        nav_buttons.append(InlineKeyboardButton(text="◀️ قبلی", callback_data=f"{page_prefix}{page-1}"))
    
    if total_pages > 1:
        nav_buttons.append(InlineKeyboardButton(text=f"صفحه {page} از {total_pages}", callback_data="ignore"))
        
    if page < total_pages:
        nav_buttons.append(InlineKeyboardButton(text="بعدی ▶️", callback_data=f"{page_prefix}{page+1}"))
    
    if nav_buttons:
        buttons.append(nav_buttons)

    buttons.append([InlineKeyboardButton(text="🔙 بازگشت به منوی پرونده‌ها", callback_data="back_to_cases_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def kb_document_upload() -> ReplyKeyboardMarkup:
    buttons = [
        [KeyboardButton(text="❌ این مدرک را ندارم")],
        [KeyboardButton(text="📤 ارسال فایل")],
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


def kb_document_submit() -> ReplyKeyboardMarkup:
    buttons = [
        [KeyboardButton(text="➕ افزودن مدرک اضافی")],
        [KeyboardButton(text="✅ تایید و ارسال برای بررسی")],
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


def kb_document_review(doc_id: int) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="✅ تایید", callback_data=f"doc_approve_{doc_id}"),
         InlineKeyboardButton(text="❌ رد", callback_data=f"doc_reject_{doc_id}")],
        [InlineKeyboardButton(text="⏩ بعدی (بدون تغییر)", callback_data=f"doc_next_{doc_id}")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def kb_ticket_actions(ticket_id: int) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="💬 پاسخ دادن", callback_data=f"ticket_reply_{ticket_id}"),
         InlineKeyboardButton(text="🔒 بستن تیکت", callback_data=f"ticket_close_{ticket_id}")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def kb_open_tickets_list(tickets: list) -> InlineKeyboardMarkup:
    buttons = []
    for t in tickets:
        subject = t['subject'] or 'بدون موضوع'
        buttons.append([InlineKeyboardButton(text=f"🎫 #{t['id']} | {subject}", callback_data=f"ticket_view_{t['id']}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def kb_status_change(case_id: str) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="🟢 سبز", callback_data=f"status_green_{case_id}"),
         InlineKeyboardButton(text="🟡 زرد", callback_data=f"status_yellow_{case_id}")],
        [InlineKeyboardButton(text="🔴 قرمز", callback_data=f"status_red_{case_id}")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def kb_yes_no(action: str) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="✅ بله", callback_data=f"confirm_{action}_yes"),
         InlineKeyboardButton(text="❌ خیر", callback_data=f"confirm_{action}_no")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def kb_license_detail(code: str) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="افزایش ظرفیت", callback_data=f"lic_cap_{code}"),
         InlineKeyboardButton(text="غیرفعال", callback_data=f"lic_deact_{code}")],
        [InlineKeyboardButton(text="مشاهده اعضا", callback_data=f"lic_members_{code}"),
         InlineKeyboardButton(text="حذف", callback_data=f"lic_del_{code}")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def kb_interview_reminder(interview_id: int) -> InlineKeyboardButton:
    return InlineKeyboardButton(text="مشاهده جزئیات", callback_data=f"interview_{interview_id}")


def kb_interview_delete_buttons(interview_id: int, is_super_admin: bool) -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text="🗑 حذف مصاحبه", callback_data=f"delete_interview_{interview_id}")]]
    if is_super_admin:
        buttons.append([InlineKeyboardButton(text="🙏 عذرخواهی می‌کنم (حذف با دلیل)", callback_data=f"delete_interview_apology_{interview_id}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def kb_case_owner_type_inline(action_prefix: str) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="🏢 موسسات", callback_data=f"{action_prefix}_type_agency"),
         InlineKeyboardButton(text="👤 کلاینت‌های مستقیم", callback_data=f"{action_prefix}_type_client")],
        [InlineKeyboardButton(text="🤳 بلاگرها", callback_data=f"{action_prefix}_type_blogger")],
        [InlineKeyboardButton(text="🔙 بازگشت به منوی پرونده‌ها", callback_data="back_to_cases_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def kb_agency_selection(agencies: list, action_prefix: str = "select_owner_lic") -> InlineKeyboardMarkup:
    buttons = []
    for ag in agencies:
        callback = f"{action_prefix}_{ag['code']}"
        buttons.append([InlineKeyboardButton(text=f"🏢 {ag['agency_name']} ({ag['code']})", callback_data=callback)])
    
    # Extract original action to determine back button
    orig_action = action_prefix.split("_")[0]
    buttons.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data=f"{orig_action}_back_to_type")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def kb_blogger_platforms() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="📸 اینستاگرام", callback_data="platform_instagram")],
        [InlineKeyboardButton(text="🌐 وب‌سایت", callback_data="platform_website")],
        [InlineKeyboardButton(text="📢 تلگرام", callback_data="platform_telegram")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def kb_blogger_selection(bloggers: list, action_prefix: str = "select_blogger_lic") -> InlineKeyboardMarkup:
    buttons = []
    for bg in bloggers:
        name = bg['agency_name'] or f"بلاگر {bg['code']}"
        callback = f"{action_prefix}_{bg['code']}"
        buttons.append([InlineKeyboardButton(text=f"🤳 {name}", callback_data=callback)])
    
    orig_action = action_prefix.split("_")[0]
    buttons.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data=f"{orig_action}_back_to_type")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def kb_scheduling_type() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="🏢 موسسات", callback_data="sched_type_agency"),
         InlineKeyboardButton(text="👤 کلاینت‌های مستقیم", callback_data="sched_type_client")],
        [InlineKeyboardButton(text="🤳 بلاگرها", callback_data="sched_type_blogger")],
        [InlineKeyboardButton(text="🔙 انصراف", callback_data="cancel_scheduling")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)
def kb_installment_management(case_id: str, installments: list) -> InlineKeyboardMarkup:
    buttons = []
    for inst in installments:
        status = "✅" if inst['is_paid'] else "❌"
        # Display mapping tags if any
        tags = []
        if inst.get('is_for_initial'): tags.append("🤝")
        if inst.get('is_for_interview'): tags.append("🎯")
        if inst.get('is_for_contract'): tags.append("📜")
        if inst.get('is_for_pre_approval'): tags.append("✅")
        tag_str = " ".join(tags)
        
        label = f"قسط {inst['idx']}: {inst['amount']}€ ({status}) {tag_str}"
        buttons.append([InlineKeyboardButton(text=label, callback_data=f"inst_toggle_{inst['id']}_{case_id}")])
        
        # Add a "Map" button for each installment
        buttons.append([InlineKeyboardButton(text=f"⚙️ تخصیص قسط {inst['idx']}", callback_data=f"inst_map_{inst['id']}_{case_id}")])
    
    buttons.append([InlineKeyboardButton(text="🔙 بازگشت به پرونده", callback_data=f"case_view_{case_id}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def kb_visa_types(selected: list = None) -> InlineKeyboardMarkup:
    selected = selected or []
    options = ["آوسبیلدونگ", "جاب آفر", "تحصیلی"]
    buttons = []
    
    for opt in options:
        status = "✅ " if opt in selected else ""
        buttons.append([InlineKeyboardButton(text=f"{status}{opt}", callback_data=f"visa_toggle_{opt}")])
    
    if selected:
        buttons.append([InlineKeyboardButton(text="✅ تایید نهایی", callback_data="visa_confirm")])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def kb_add_more_fields() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="➕ افزودن رشته دیگر", callback_data="field_add_more")],
        [InlineKeyboardButton(text="✅ تکمیل و مرحله بعد", callback_data="field_finish_adding")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def kb_field_selection(fields: list, prefix: str) -> InlineKeyboardMarkup:
    buttons = []
    for f in fields:
        buttons.append([InlineKeyboardButton(text=f"🎓 {f['field_name']}", callback_data=f"{prefix}{f['id']}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def kb_installment_mapping(installments: list, current_idx: int, mapping: dict) -> InlineKeyboardMarkup:
    # installments: list of dicts with 'idx' and 'amount'
    # current_idx: index of installment being mapped (0-based)
    # mapping: dict {idx: [events]}
    
    inst = installments[current_idx]
    # Standardize: Convert all keys to string for reliable checkmark display
    str_mapping = {str(k): v for k, v in mapping.items()}
    events = str_mapping.get(str(inst['idx']), [])
    
    # DEBUG: print mapping for troubleshooting
    print(f"DEBUG: inst_idx={inst['idx']}, events={events}, full_mapping={str_mapping}")
    
    options = [
        ("initial", "🤝 عقد قرارداد (قسط اول)"),
        ("interview", "🎯 مصاحبه"),
        ("contract", "📜 قرارداد کارفرما"),
        ("preapproval", "📋 پیش‌تاییدیه")
    ]
    
    buttons = []
    for key, label in options:
        status = "✅ " if key in events else "❌ "
        buttons.append([InlineKeyboardButton(text=f"{status}{label}", callback_data=f"map_toggle_{inst['idx']}_{key}")])
    
    buttons.append([InlineKeyboardButton(text="➡️ بعدی / تایید این قسط", callback_data=f"map_next_{inst['idx']}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def kb_admin_payment_notification(case_id: str, installment_id: int, reminder_id: int) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="✅ پرداخت شد", callback_data=f"admin_paid_{installment_id}_{reminder_id}")],
        [InlineKeyboardButton(text="📋 مشاهده پرونده", callback_data=f"case_view_{case_id}")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def kb_client_payment_notification(case_id: str) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="📝 مشاهده قرارداد اصلی", callback_data=f"case_contract_{case_id}")],
        [InlineKeyboardButton(text="📋 جزئیات پرونده", callback_data=f"case_view_{case_id}")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def kb_user_ticket_actions(ticket_id: int) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="💬 ارسال پیام جدید", callback_data=f"ticket_reply_{ticket_id}")],
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="back_to_tickets")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def kb_client_license_selection(clients: list, action_prefix: str = "select_client_lic") -> InlineKeyboardMarkup:
    buttons = []
    for client in clients:
        name = client['agency_name'] or f"کلاینت {client['code']}"
        callback = f"{action_prefix}_{client['code']}"
        buttons.append([InlineKeyboardButton(text=f"👤 {name}", callback_data=callback)])
    
    orig_action = action_prefix.split("_")[0]
    buttons.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data=f"{orig_action}_back_to_type")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def kb_apology_reason_selection(interview_id: int) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="✅ بله", callback_data=f"apology_reason_yes_{interview_id}"),
         InlineKeyboardButton(text="❌ خیر", callback_data=f"apology_reason_no_{interview_id}")],
        [InlineKeyboardButton(text="🔙 انصراف", callback_data=f"apology_reason_cancel_{interview_id}")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)
