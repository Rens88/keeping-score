from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypedDict, cast

from tournament_tracker.config import AppConfig
from tournament_tracker.models import User, UserWithProfile, utc_now_iso
from tournament_tracker.repository import SQLiteRepository
from tournament_tracker.security import hash_password
from tournament_tracker.services.errors import ValidationError


OptionKey = Literal["A", "B", "C", "D"]

LOCATION_ANSWER = "Erp"
MAX_REGISTRATION_GAME_POINTS = 10
REGISTRATION_GAME_SETTING_KEY = "registration_game_active"
DEFAULT_PARTICIPANT_MOTTO = "Still warming up for the weekend."


class RegistrationGameOption(TypedDict):
    key: OptionKey
    label: str


class RegistrationGameQuestion(TypedDict):
    question: str
    options: tuple[RegistrationGameOption, RegistrationGameOption, RegistrationGameOption, RegistrationGameOption]
    correctAnswer: OptionKey
    hint: str


@dataclass(frozen=True, slots=True)
class RegistrationQuestionResult:
    question_number: int
    is_correct: bool
    selected_option_key: OptionKey
    selected_option_label: str
    correct_option_key: OptionKey
    correct_option_label: str
    hint: str
    questions_answered: int
    incorrect_answers: int


@dataclass(frozen=True, slots=True)
class RegistrationGuessResult:
    is_correct: bool
    normalized_guess: str
    points_awarded: int | None = None


class RegistrationService:
    QUESTIONS: tuple[RegistrationGameQuestion, ...] = (
        {
            "question": "Hoe heet de indeling van een kompas in 32 delen NIET?",
            "options": (
                {"key": "A", "label": "Windrichting"},
                {"key": "B", "label": "Windstreek"},
                {"key": "C", "label": "Kompasroos"},
                {"key": "D", "label": "Hemelstreek"},
            ),
            "correctAnswer": "C",
            "hint": "De bestemming ligt (t.o.v. de sporthal) in het zuidoosten.",
        },
        {
            "question": "Hoeveel graden is een rechte hoek?",
            "options": (
                {"key": "A", "label": "45"},
                {"key": "B", "label": "90"},
                {"key": "C", "label": "180"},
                {"key": "D", "label": "270"},
            ),
            "correctAnswer": "B",
            "hint": "Je moet ongeveer 150 graden draaien vanaf het noorden.",
        },
        {
            "question": "Welke provincie ligt ten zuidoosten van Utrecht?",
            "options": (
                {"key": "A", "label": "Gelderland"},
                {"key": "B", "label": "Noord-Brabant"},
                {"key": "C", "label": "Limburg"},
                {"key": "D", "label": "Zuid-Holland"},
            ),
            "correctAnswer": "B",
            "hint": "Bourgondisch, zachte G.",
        },
        {
            "question": "Welke van deze steden ligt het dichtst bij de bestemming?",
            "options": (
                {"key": "A", "label": "Amersfoort"},
                {"key": "B", "label": "Arnhem"},
                {"key": "C", "label": "Veghel"},
                {"key": "D", "label": "Zwolle"},
            ),
            "correctAnswer": "C",
            "hint": "De eindlocatie ligt net onder deze plaats.",
        },
        {
            "question": "Welke van deze plaatsen ligt in Noord-Brabant?",
            "options": (
                {"key": "A", "label": "Tiel"},
                {"key": "B", "label": "Veghel"},
                {"key": "C", "label": "Zeist"},
                {"key": "D", "label": "Harderwijk"},
            ),
            "correctAnswer": "B",
            "hint": "De bestemming ligt in de buurt van Veghel.",
        },
        {
            "question": "Wat is een kenmerk van veel Brabantse dorpen?",
            "options": (
                {"key": "A", "label": "Grote wolkenkrabbers"},
                {"key": "B", "label": "Kerkplein in het centrum"},
                {"key": "C", "label": "Metrostations"},
                {"key": "D", "label": "Industriehavens"},
            ),
            "correctAnswer": "B",
            "hint": "De bestemming is geen stad.",
        },
        {
            "question": "Wat is de uitkomst van: √9 ?",
            "options": (
                {"key": "A", "label": "2"},
                {"key": "B", "label": "3"},
                {"key": "C", "label": "4"},
                {"key": "D", "label": "9"},
            ),
            "correctAnswer": "B",
            "hint": "De naam van de bestemming bestaat uit 3 letters.",
        },
        {
            "question": "Welke van deze letters is een medeklinker?",
            "options": (
                {"key": "A", "label": "A"},
                {"key": "B", "label": "E"},
                {"key": "C", "label": "O"},
                {"key": "D", "label": "R"},
            ),
            "correctAnswer": "D",
            "hint": "Deze letter zit in de naam van de bestemming.",
        },
        {
            "question": "Welk woord rijmt op “terp”?",
            "options": (
                {"key": "A", "label": "Kerk"},
                {"key": "B", "label": "Dorp"},
                {"key": "C", "label": "Erp"},
                {"key": "D", "label": "Werf"},
            ),
            "correctAnswer": "C",
            "hint": "Denk aan een Groningse heuvel.",
        },
        {
            "question": "Wat is de bestemming?",
            "options": (
                {"key": "A", "label": "Ede"},
                {"key": "B", "label": "Epe"},
                {"key": "C", "label": "Erp"},
                {"key": "D", "label": "Uden"},
            ),
            "correctAnswer": "C",
            "hint": "Het antwoord is: Erp",
        },
    )

    def __init__(self, repo: SQLiteRepository, config: AppConfig) -> None:
        self.repo = repo
        self.config = config

    def list_questions(self) -> tuple[RegistrationGameQuestion, ...]:
        return self.QUESTIONS

    def get_question(self, question_index: int) -> RegistrationGameQuestion:
        return self.QUESTIONS[question_index]

    @staticmethod
    def get_option_map(question: RegistrationGameQuestion) -> dict[OptionKey, str]:
        return {option["key"]: option["label"] for option in question["options"]}

    @staticmethod
    def calculate_score(incorrect_answers: int) -> int:
        return max(0, MAX_REGISTRATION_GAME_POINTS - incorrect_answers)

    def is_registration_game_active(self) -> bool:
        setting = self.repo.get_app_setting(REGISTRATION_GAME_SETTING_KEY)
        return (setting or "").strip().lower() == "true"

    def set_registration_game_active(self, *, admin_user_id: int, active: bool) -> None:
        now_iso = utc_now_iso()
        self.repo.set_app_setting(
            key=REGISTRATION_GAME_SETTING_KEY,
            value="true" if active else "false",
            updated_at=now_iso,
        )
        state_label = "activated" if active else "paused"
        self.repo.log_activity(
            event_type="registration_game_toggle",
            message=f"Admin {state_label} the registration game",
            created_at=now_iso,
            related_user_id=admin_user_id,
        )

    def participant_requires_registration_gate(self, user: User) -> bool:
        return user.role == "participant" and not user.registration_game_completed

    def create_admin_managed_participant(
        self,
        *,
        admin_user_id: int,
        display_name: str,
        username: str,
        password: str,
        email: str | None = None,
    ) -> User:
        clean_display_name = (display_name or "").strip()
        clean_username = (username or "").strip()
        clean_password = password or ""
        clean_email = ((email or "").strip().lower()) or None

        if len(clean_display_name) < 2 or len(clean_display_name) > 80:
            raise ValidationError("Display name must be between 2 and 80 characters.")
        if len(clean_username) < 3 or len(clean_username) > 40:
            raise ValidationError("Username must be between 3 and 40 characters.")
        if " " in clean_username:
            raise ValidationError("Username cannot contain spaces.")
        if len(clean_password) < 4:
            raise ValidationError("Password must be at least 4 characters.")
        if self.repo.get_user_by_username(clean_username):
            raise ValidationError("That username is already in use.")
        if clean_email and self.repo.get_user_by_email(clean_email):
            raise ValidationError("That email is already in use.")

        now_iso = utc_now_iso()
        user = self.repo.create_admin_managed_participant(
            username=clean_username,
            email=clean_email,
            password_hash=hash_password(clean_password),
            display_name=clean_display_name,
            motto=DEFAULT_PARTICIPANT_MOTTO,
            created_by_admin_user_id=admin_user_id,
            now_iso=now_iso,
        )
        self.repo.log_activity(
            event_type="participant_created_admin",
            message=f"Admin created registration account for {clean_display_name}",
            created_at=now_iso,
            related_user_id=user.id,
        )
        return user

    def build_registration_invitation(
        self,
        *,
        display_name: str,
        username: str,
        password: str,
    ) -> str:
        app_link = self.config.app_base_url or "/"
        safe_name = display_name.strip() or username.strip()
        safe_username = username.strip()
        safe_password = password
        return (
            f"Hey {safe_name}! Your registration mission has arrived.\n\n"
            f"Open this glorious link: {app_link}\n"
            f"Username: {safe_username}\n"
            f"Password: {safe_password}\n\n"
            "Please register with the urgency of someone protecting the last bitterbal at teamweekend. "
            "The admin dashboard is watching, the leaderboard is judging, and your future glory refuses to wait."
        )

    def get_unlocked_hints(self, user: UserWithProfile | User) -> list[str]:
        unlocked_count = max(0, min(user.registration_questions_answered, len(self.QUESTIONS)))
        return [question["hint"] for question in self.QUESTIONS[:unlocked_count]]

    def can_submit_guess(self, user: User) -> bool:
        if user.registration_game_completed or user.role != "participant":
            return False
        if user.registration_questions_answered <= 0:
            return False
        if user.registration_questions_answered >= len(self.QUESTIONS):
            return True
        return user.registration_game_guesses_used < user.registration_questions_answered

    def can_answer_next_question(self, user: User) -> bool:
        if user.registration_game_completed or user.role != "participant":
            return False
        if user.registration_questions_answered >= len(self.QUESTIONS):
            return False
        return user.registration_game_guesses_used >= user.registration_questions_answered

    def answer_next_question(
        self,
        *,
        user_id: int,
        selected_option_key: str,
    ) -> RegistrationQuestionResult:
        user = self._require_participant(user_id)
        if not self.can_answer_next_question(user):
            raise ValidationError("Use your current guess chance before moving on to the next question.")

        question = self.QUESTIONS[user.registration_questions_answered]
        option_key = selected_option_key.strip().upper()
        option_map = self.get_option_map(question)
        if option_key not in option_map:
            raise ValidationError("Please choose one of the answer options.")

        selected_option_key_typed = cast(OptionKey, option_key)
        correct_option_key = question["correctAnswer"]
        is_correct = selected_option_key_typed == correct_option_key
        incorrect_answers = user.registration_game_incorrect_answers + (0 if is_correct else 1)
        questions_answered = user.registration_questions_answered + 1
        now_iso = utc_now_iso()
        selected_option_label = option_map[selected_option_key_typed]

        self.repo.update_registration_game_progress(
            user_id=user_id,
            questions_answered=questions_answered,
            guesses_used=user.registration_game_guesses_used,
            incorrect_answers=incorrect_answers,
            completed=user.registration_game_completed,
            points=user.registration_game_points,
            completed_at=user.registration_game_completed_at,
            updated_at=now_iso,
        )

        return RegistrationQuestionResult(
            question_number=questions_answered,
            is_correct=is_correct,
            selected_option_key=selected_option_key_typed,
            selected_option_label=selected_option_label,
            correct_option_key=correct_option_key,
            correct_option_label=option_map[correct_option_key],
            hint=question["hint"],
            questions_answered=questions_answered,
            incorrect_answers=incorrect_answers,
        )

    def submit_location_guess(self, *, user_id: int, guess: str) -> RegistrationGuessResult:
        user = self._require_participant(user_id)
        clean_guess = (guess or "").strip()
        if not clean_guess:
            raise ValidationError("Enter a location guess first.")
        if not self.can_submit_guess(user):
            raise ValidationError("Answer the current question before making a guess.")

        normalized_guess = clean_guess.casefold()
        normalized_answer = LOCATION_ANSWER.casefold()
        now_iso = utc_now_iso()

        if normalized_guess == normalized_answer:
            awarded_points = self.calculate_score(user.registration_game_incorrect_answers)
            self.repo.update_registration_game_progress(
                user_id=user_id,
                questions_answered=user.registration_questions_answered,
                guesses_used=user.registration_game_guesses_used,
                incorrect_answers=user.registration_game_incorrect_answers,
                completed=True,
                points=awarded_points,
                completed_at=now_iso,
                updated_at=now_iso,
            )
            self.repo.log_activity(
                event_type="registration_game_completed",
                message=f"Participant {user_id} completed the registration game with {awarded_points} points",
                created_at=now_iso,
                related_user_id=user_id,
            )
            return RegistrationGuessResult(
                is_correct=True,
                normalized_guess=clean_guess,
                points_awarded=awarded_points,
            )

        guesses_used = user.registration_game_guesses_used
        if user.registration_questions_answered < len(self.QUESTIONS):
            guesses_used += 1

        self.repo.update_registration_game_progress(
            user_id=user_id,
            questions_answered=user.registration_questions_answered,
            guesses_used=guesses_used,
            incorrect_answers=user.registration_game_incorrect_answers,
            completed=False,
            points=user.registration_game_points,
            completed_at=user.registration_game_completed_at,
            updated_at=now_iso,
        )
        return RegistrationGuessResult(is_correct=False, normalized_guess=clean_guess)

    def _require_participant(self, user_id: int) -> User:
        user = self.repo.get_user_by_id(user_id)
        if not user or user.role != "participant":
            raise ValidationError("Participant account not found.")
        if user.registration_game_completed:
            raise ValidationError("This registration game is already complete.")
        return user
