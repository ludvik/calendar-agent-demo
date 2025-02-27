## Real Estate Calendar Agent Target User Stories

## Core Use Cases

### 1. Basic Appointment Scheduling
**Scenario**:  
New agent David needs to schedule his first property viewing

**User Input**:  
"Schedule a condo viewing at 123 Main St for tomorrow 2-3pm"

**Tool Calls**:
```python
schedule_appointment(
    title="Condo Viewing - 123 Main St",
    start_time="2025-03-02T14:00",
    duration=60,
    priority=3
)
```

**Tool Response**:
```json
{
    "scheduled": true,
    "appointment_id": 101,
    "conflicts": []
}
```

**Agent Response**:  
"Scheduled: Condo Viewing at 123 Main St for Sun Mar 2nd 2:00-3:00 PM."

---

### 2. Priority Conflict Resolution
**Scenario**:  
Agent Lisa needs to schedule a $5M luxury home viewing conflicting with existing appointments

**Conversation Flow**:

**User**: "Need to show 456 Luxury Lane today 3-5pm. This is high priority!"

**Tool Calls** (First Round):
```python
# Directly schedule the high-priority appointment
schedule_appointment(
    title="Luxury Home Viewing - 456 Luxury Lane",
    time="2025-03-01T15:00",
    duration=120,
    priority=2
)
```

**Tool Response**:
```json
{
    "success": true,
    "appointment": {
        "id": 201,
        "title": "Luxury Home Viewing - 456 Luxury Lane",
        "time": "2025-03-01T15:00",
        "duration": 120,
        "priority": 2
    },
    "conflicts": [
        {
            "id": 102,
            "title": "Apartment Tour",
            "time": "2025-03-01T15:30",
            "duration": 60,
            "priority": 3,
            "type": "client_meeting"
        },
        {
            "id": 103,
            "title": "Team Meeting",
            "time": "2025-03-01T16:00",
            "duration": 30,
            "priority": 4,
            "type": "internal"
        },
        {
            "id": 104,
            "title": "Property Paperwork Review",
            "time": "2025-03-01T16:30",
            "duration": 30,
            "priority": 3,
            "type": "internal"
        }
    ]
}
```

**Agent**: "I've scheduled the luxury home viewing at 456 Luxury Lane today from 3:00-5:00 PM. 

I noticed this conflicts with:
1. Apartment Tour at 3:30pm (client meeting)
2. Team Meeting at 4:00pm (internal)
3. Property Paperwork Review at 4:30pm (internal)

How would you like me to handle these conflicting appointments?"

**User**: "Move all internal meetings to tomorrow morning and try to reschedule the apartment tour for later today if possible."

**Tool Calls** (Second Round):
```python
# Batch resolve conflicts for the already created appointment
resolve_conflicts(
    for_appointment_id=201,
    strategies={
        "by_type": {
            "internal": {"action": "reschedule", "target_window": "2025-03-02T09:00-12:00"},
            "client_meeting": {"action": "reschedule", "target_window": "2025-03-01T17:00-19:00"}
        }
    }
)
```

**Tool Response**:
```json
{
    "resolved_conflicts": [
        {
            "id": 103,
            "title": "Team Meeting",
            "action": "rescheduled",
            "original_time": "2025-03-01T16:00",
            "new_time": "2025-03-02T09:30",
            "notification_sent": true
        },
        {
            "id": 104,
            "title": "Property Paperwork Review",
            "action": "rescheduled",
            "original_time": "2025-03-01T16:30",
            "new_time": "2025-03-02T10:30",
            "notification_sent": true
        }
    ],
    "unresolved_conflicts": [
        {
            "id": 102,
            "title": "Apartment Tour",
            "reason": "No available slots in target window",
            "alternatives": [
                {"time": "2025-03-01T09:00", "duration": 60},
                {"time": "2025-03-02T15:00", "duration": 60}
            ]
        }
    ]
}
```

**Agent**: "I've handled the conflicting appointments:

Successfully rescheduled:
   - Team Meeting → tomorrow at 9:30am
   - Property Paperwork Review → tomorrow at 10:30am

Could not reschedule the Apartment Tour for later today. Options:
   1. Tomorrow morning at 9:00am
   2. Tomorrow afternoon at 3:00pm
   
How would you like to handle the Apartment Tour?"

**User**: "Let's go with tomorrow at 3pm for the apartment tour."

**Tool Calls** (Third Round):
```python
reschedule_appointment(
    appointment_id=102,
    new_time="2025-03-02T15:00",
    duration=60,
    send_notification=true
)
```

**Tool Response**:
```json
{
    "success": true,
    "appointment": {
        "id": 102,
        "title": "Apartment Tour",
        "original_time": "2025-03-01T15:30",
        "new_time": "2025-03-02T15:00",
        "notification_sent": true
    }
}
```

**Agent**: "Perfect! I've completed all scheduling:

1. Luxury Home Viewing confirmed for today 3:00-5:00 PM
2. Apartment Tour moved to tomorrow at 3:00 PM
3. Team Meeting moved to tomorrow at 9:30 AM
4. Property Paperwork Review moved to tomorrow at 10:30 AM

All affected parties have been notified. Is there anything else you need for the luxury home showing?"

---

### 3. Flexible Duration Adjustment
**Scenario**:  
Client requests extending a showing from 60 to 90 minutes

**User Input**:  
"Can we extend the 2pm showing to 90 minutes?"

**Tool Calls**:
```python
check_availability(
    appointment_id=205,
    new_duration=90
)
```

**Tool Response**:
```json
{
    "available": false,
    "conflicts": [
        {"id": 207, "title": "Team Meeting", "priority": 3}
    ],
    "resolution_options": ["reschedule_conflict", "split_showings"]
}
```

**Agent Response**:  
"Extension would conflict with existing appointments. Suggest rescheduling conflicting meeting or splitting showing into two sessions."

---

### 5. VIP Client Priority Escalation
**Scenario**:  
A VIP client needs immediate attention during busy hours

**User Input**:  
"Make space for Mr. Smith's urgent request at 4pm today"

**Tool Calls**:
```python
smart_schedule(
    title="VIP Client Meeting",
    desired_time="2025-03-01T16:00",
    duration=60,
    priority=1
)
```

**Tool Response**:
```json
{
    "scheduled": true,
    "method": "override",
    "cancelled_appointments": [301, 302],
    "client_notifications_sent": 2
}
```

**Agent Response**:  
"Scheduled VIP meeting at 4:00 PM by rescheduling 2 lower-priority appointments. Clients have been notified."

---

## Extended Use Cases

### 3. Batch Open House Management
**Scenario**:  
Coordinating weekend open houses for 3 new luxury properties

**User Input**:  
"Set up open houses for 789 Elite Blvd, Sat-Sun 10am-4pm"

**Tool Calls**:
```python
bulk_schedule_appointments(
    properties=["789 Elite Blvd"],
    days=["2025-03-08", "2025-03-09"],
    window_start="10:00",
    window_end="16:00",
    priority=2
)
```

**Tool Response**:
```json
{
    "scheduled_count": 6,
    "conflicts_resolved": 2,
    "failed_slots": []
}
```

**Agent Response**:  
"Created 6 open house slots. Resolved 2 scheduling conflicts. All slots confirmed."

---

### 6. Lead Follow-up Scheduling
**Scenario**:  
Schedule follow-up calls with new leads

**User Input**:  
"Schedule follow-up with lead 101 for tomorrow 10am"

**Tool Calls**:
```python
schedule_follow_up(
    lead_id=101,
    follow_up_time="2025-03-02T10:00"
)
```

**Tool Response**:
```json
{
    "scheduled": true,
    "follow_up_id": 201,
    "reminder_sent": true
}
```

**Agent Response**:  
"Follow-up scheduled for tomorrow 10:00 AM. Reminder sent to lead."

---

### 7. Open House Promotion
**Scenario**:  
Promote open house events on social media

**User Input**:  
"Promote open house at 789 Elite Blvd on Facebook and Twitter"

**Tool Calls**:
```python
promote_open_house(
    event_id=202,
    social_media_platforms=["Facebook", "Twitter"]
)
```

**Tool Response**:
```json
{
    "promoted": true,
    "posts": [
        {"platform": "Facebook", "post_id": 123},
        {"platform": "Twitter", "post_id": 456}
    ]
}
```

**Agent Response**:  
"Open house promoted on Facebook and Twitter. Posts created."

---

### 8. Client Communication Automation
**Scenario**:  
Automate routine client communication, such as sending reminders and updates

**User Input**:  
"Send reminder to client 303 about upcoming showing"

**Tool Calls**:
```python
automate_client_communication(
    client_id=303,
    communication_type="reminder"
)
```

**Tool Response**:
```json
{
    "sent": true,
    "message_id": 901
}
```

**Agent Response**:  
"Reminder sent to client. Message ID: 901."

---

### 9. Market Analysis Report Generation
**Scenario**:  
Generate market analysis reports for clients

**User Input**:  
"Generate market analysis report for client 404"

**Tool Calls**:
```python
generate_market_analysis_report(
    client_id=404,
    report_type="monthly"
)
```

**Tool Response**:
```json
{
    "generated": true,
    "report_id": 111,
    "report_url": "https://example.com/report/111"
}
```

**Agent Response**:  
"Market analysis report generated. Report ID: 111. URL: https://example.com/report/111."

---

### 10. Transaction Management
**Scenario**:  
Manage transactions, including document signing and payment processing

**User Input**:  
"Process payment for transaction 505"

**Tool Calls**:
```python
manage_transaction(
    transaction_id=505,
    action="process_payment"
)
```

**Tool Response**:
```json
{
    "processed": true,
    "payment_id": 222,
    "payment_status": "paid"
}
```

**Agent Response**:  
"Payment processed for transaction 505. Payment ID: 222. Status: Paid."

---

## Extended Use Cases

### 1. Handling Last-Minute Cancellations
**Scenario**:  
Client cancels Thursday morning showing, agent Sarah needs to quickly fill this gap.

**User Input**:  
"Client canceled Thursday 9-11am showing. Find something to move into this slot."

**Tool Calls**:
```python
reschedule_low_priority(
    target_window="2025-03-06T09:00-11:00",
    min_priority=3
)
```

**Tool Response**:
```json
[
    {
        "original_appointment": {"id": 305, "title": "Investment Property Review"},
        "new_time": "2025-03-06T09:30-10:30",
        "client_notified": true
    }
]
```

---

### 2. Finding Multiple Available Slots
**Scenario**:  
Agent needs to propose 3 viable time slots across the next week for a client meeting.

**User Input**:  
"Find 3 times over the next week I could offer to my VIP client for a 2-hour meeting."

**Tool Calls**:
```python
find_optimal_slots(
    time_range=("2025-03-01T09:00", "2025-03-07T17:00"),
    duration=120,
    min_open_score=0.7,  # Day openness threshold 
    preferred_hours=[(9,12), (14,17)],
    max_results=3
)
```

**Tool Response**:
```json
{
    "recommended_slots": [
        {"start": "2025-03-01T10:00", "end": "2025-03-01T12:00", "score": 0.85},
        {"start": "2025-03-03T14:00", "end": "2025-03-03T16:00", "score": 0.78},
        {"start": "2025-03-05T09:30", "end": "2025-03-05T11:30", "score": 0.72}
    ],
    "day_analysis": {
        "2025-03-01": {"open_score": 0.85, "meeting_density": 0.2},
        "2025-03-03": {"open_score": 0.78, "meeting_density": 0.15},
        "2025-03-05": {"open_score": 0.72, "meeting_density": 0.3}
    }
}
```

**Verification Points**:  
 Intelligently evaluates day openness using scoring algorithm  
 Respects client's preferred working hours  
 Prioritizes days with lower meeting density  
 Provides detailed day-by-day analysis