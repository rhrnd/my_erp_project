from django import forms
from datetime import datetime


def get_year_choices():
    current_year = datetime.now().year
    # 1998년부터 현재 연도까지 역순(최신순)으로 생성
    # key를 str로 통일: ChoiceField cleaned_data, initial 모두 문자열이므로 일관성 유지
    return [(str(year), f"{year}년") for year in range(current_year, 1997, -1)]


def get_month_choices():
    return [(str(month), f"{month:02d}월") for month in range(1, 13)]


class SalarySearchForm(forms.Form):
    year = forms.ChoiceField(
        choices=get_year_choices,
        label="",
        # d-inline-block과 너비(width)를 지정하여 버튼 옆에 예쁘게 배치합니다.
        widget=forms.Select(attrs={
            'class': 'form-select d-inline-block',
            'style': 'width: 120px;'
        })
    )
    month = forms.ChoiceField(
        choices=get_month_choices,
        label="",
        widget=forms.Select(attrs={
            'class': 'form-select d-inline-block',
            'style': 'width: 100px;'
        })
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        now = datetime.now()
        self.fields['year'].initial = str(now.year)  # ChoiceField는 문자열 비교가 안전할 때가 있습니다.
        self.fields['month'].initial = str(now.month)


class PtoSearchForm(forms.Form):
    year = forms.ChoiceField(
        choices=get_year_choices,
        label="",
        widget=forms.Select(attrs={
            'class': 'form-select d-inline-block',
            'style': 'width: 120px;'
        })
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['year'].initial = str(datetime.now().year)
