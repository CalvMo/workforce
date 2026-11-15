from django import forms

from .models import LeaveRequest, LeaveType


class DateInput(forms.DateInput):
    input_type = "date"


class LeaveRequestForm(forms.ModelForm):
    class Meta:
        model = LeaveRequest
        fields = ["leave_type", "start_date", "end_date", "start_half_day", "end_half_day", "reason", "attachment"]
        widgets = {"start_date": DateInput(), "end_date": DateInput(), "reason": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["leave_type"].queryset = LeaveType.objects.filter(active=True)


class DecisionForm(forms.Form):
    comment = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))
