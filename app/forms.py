from flask_wtf import FlaskForm
from wtforms import BooleanField, EmailField, FloatField, IntegerField, PasswordField, SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Email, EqualTo, Length, NumberRange, Optional, Regexp


class LoginForm(FlaskForm):
    email = EmailField("Email", validators=[DataRequired(), Email()])
    password = PasswordField("Пароль", validators=[DataRequired()])
    remember = BooleanField("Запомнить меня")
    submit = SubmitField("Войти")


class RegisterForm(FlaskForm):
    name = StringField("Имя", validators=[Optional(), Length(max=120)])
    email = EmailField("Email", validators=[DataRequired(), Email()])
    password = PasswordField("Пароль", validators=[DataRequired(), Length(min=8)])
    password2 = PasswordField(
        "Повторите пароль",
        validators=[DataRequired(), EqualTo("password", message="Пароли не совпадают")],
    )
    submit = SubmitField("Создать аккаунт")


class CreateProjectForm(FlaskForm):
    project_name = StringField(
        "Название проекта",
        validators=[
            DataRequired(),
            Length(max=64),
            Regexp(r"^[a-zA-Z0-9_-]+$", message="Только буквы, цифры, _ и -"),
        ],
    )
    source_language = SelectField("Язык оригинала", validators=[DataRequired()])
    target_language = SelectField("Язык дубляжа", validators=[DataRequired()])
    voice_gender = SelectField(
        "Пол голоса",
        choices=[("", "Авто"), ("male", "Мужской"), ("female", "Женский")],
        validators=[Optional()],
    )
    voice_age = IntegerField(
        "Возраст голоса",
        validators=[Optional(), NumberRange(min=5, max=90)],
    )
    voice_prompt = TextAreaField(
        "Промпт голоса",
        validators=[Optional(), Length(max=500)],
        render_kw={"placeholder": "Natural {gender_hint}, {lang}. {age_hint}."},
    )
    dub_volume_percent = IntegerField(
        "Громкость дубляжа (%)",
        default=100,
        validators=[Optional(), NumberRange(min=0, max=200)],
    )
    original_audio_ratio = StringField(
        "Доля оригинала",
        default="0.3",
        validators=[Optional()],
    )
    voice_design_temperature = FloatField(
        "Креативность TTS",
        default=0.72,
        validators=[Optional(), NumberRange(min=0, max=1)],
    )
    voice_sample_male_ref_text = TextAreaField(
        "Текст мужского сэмпла",
        validators=[Optional(), Length(max=500)],
    )
    voice_sample_female_ref_text = TextAreaField(
        "Текст женского сэмпла",
        validators=[Optional(), Length(max=500)],
    )
    silero_speaker = SelectField(
        "Silero спикер",
        choices=[
            ("", "Не использовать"),
            ("aidar", "Aidar (♂)"),
            ("eugene", "Eugene (♂)"),
            ("baya", "Baya (♀)"),
            ("kseniya", "Kseniya (♀)"),
            ("xenia", "Xenia (♀)"),
        ],
        validators=[Optional()],
    )
    silero_all_replicas = BooleanField("Озвучить все реплики этим спикером")
    submit = SubmitField("Запустить дубляж")


class AdminUserForm(FlaskForm):
    name = StringField("Имя", validators=[Optional(), Length(max=120)])
    email = EmailField("Email", validators=[DataRequired(), Email()])
    is_admin = BooleanField("Администратор")
    is_active_user = BooleanField("Активен", default=True)
    email_verified = BooleanField("Email подтверждён")
    new_password = PasswordField("Новый пароль", validators=[Optional(), Length(min=8)])
    submit = SubmitField("Сохранить")
