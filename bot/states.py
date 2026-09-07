from aiogram.fsm.state import State, StatesGroup


class Onboarding(StatesGroup):
    waiting_for_license = State()
    waiting_for_contact = State()
    waiting_for_agency_name = State()
    waiting_for_agency_phone = State()
    waiting_for_agency_address = State()
    waiting_for_blogger_platform = State()
    waiting_for_blogger_platform_address = State()


class LicenseManagement(StatesGroup):
    selecting_action = State()
    entering_agency_name = State()
    entering_blogger_name = State()
    entering_client_name = State()
    entering_capacity = State()
    selecting_license = State()
    entering_new_capacity = State()
    selecting_user_to_kick = State()
    selecting_special_institution = State()


class CaseManagement(StatesGroup):
    selecting_action = State()
    selecting_owner_type = State()
    selecting_agency = State()
    entering_client_name = State()
    entering_total_amount = State()
    entering_installments_count = State()
    entering_installment_amount = State()
    mapping_installments = State() # New state for mapping installments to events
    entering_field_of_study = State()
    adding_fields = State()
    entering_visa_type = State()
    entering_payment_notes = State()
    selecting_case = State()
    waiting_for_edit_value = State()
    waiting_for_installment_edit = State()
    confirming_delete = State()
    editing_counter = State()
    selecting_field_for_counter = State()
    selecting_field_for_status = State()
    entering_status_reason = State()
    entering_case_comment = State()
    confirming_comment_visibility = State()
    editing_case_comment = State()
    
    # Field management for existing cases
    adding_new_field = State()
    confirming_delete_field = State()
    
    # Contract Management
    waiting_for_contract = State()
    waiting_for_contract_edit = State()
    
    # Employer Contract and Pre-approval
    waiting_for_employer_contract = State()
    waiting_for_pre_approval = State()
    
    # New states for separated view/edit/delete
    viewing_selecting_owner_type = State()
    viewing_selecting_agency = State()
    viewing_selecting_client = State()
    
    editing_selecting_owner_type = State()
    editing_selecting_agency = State()
    editing_selecting_client = State()
    
    deleting_selecting_owner_type = State()
    deleting_selecting_agency = State()
    deleting_selecting_client = State()


class DocumentUpload(StatesGroup):
    selecting_case = State()
    uploading_doc = State()
    adding_extra_docs = State()
    confirming_submit = State()


class DocumentReview(StatesGroup):
    reviewing_docs = State()
    entering_rejection_reason = State()


class TicketManagement(StatesGroup):
    selecting_action = State()
    creating_ticket = State()
    entering_subject = State()
    selecting_ticket = State()
    entering_reply = State()


class InterviewManagement(StatesGroup):
    selecting_action = State()
    selecting_owner_type = State()
    selecting_agency = State()
    selecting_client = State()
    selecting_case = State()
    entering_email_text = State()
    selecting_field = State()  # New state for selecting the major for the interview
    confirming_extraction = State()
    editing_interview = State()
    editing_field = State()  # New state for step-by-step editing
    entering_date = State()  # For separate date input
    entering_time = State()  # For separate time input
    entering_followup_notes = State()
    confirming_interview_delete = State()
    asking_apology_reason = State()
    entering_apology_reason_text = State()


class MessageManagement(StatesGroup):
    selecting_action = State()
    selecting_recipient_type = State()
    selecting_agency = State()
    selecting_client = State()
    selecting_case = State()
    entering_message_text = State()
    selecting_filters = State()
    entering_schedule_time = State()


class AdminManagement(StatesGroup):
    selecting_action = State()
    entering_admin_id = State()
    selecting_admin_to_remove = State()
    selecting_admin_to_manage = State()
    toggling_permission = State()
    confirming_super_admin = State()
    entering_super_admin_id = State()
    

class InstallmentReminder(StatesGroup):
    selecting_owner_type = State()
    selecting_agency = State()
    selecting_case = State()
    selecting_installment = State()
    asking_for_note = State()
    entering_note = State()


class SMSTest(StatesGroup):
    entering_phone = State()
    entering_message = State()
    waiting_for_2fa = State()
