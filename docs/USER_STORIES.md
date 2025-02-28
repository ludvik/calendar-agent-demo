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
batch_update(
    calendar_id=1,
    updates=[
        {
            "appointment_id": 102,
            "start_time": "2025-03-01T14:00",
            "end_time": "2025-03-01T15:00",
            "status": "CONFIRMED"
        },
        {
            "appointment_id": 103,
            "title": "Important Client Meeting",
            "start_time": "2025-03-01T09:00",
            "end_time": "2025-03-01T10:00",
            "priority": 1,
            "status": "CONFIRMED"
        }
    ]
)
```

**Tool Response**:
```json
{
    "success": true,
    "updated_appointments": [
        {
            "id": 102,
            "title": "Apartment Tour - 456 Oak Ave",
            "start_time": "2025-03-01T14:00",
            "end_time": "2025-03-01T15:00",
            "status": "CONFIRMED"
        },
        {
            "id": 103,
            "title": "Important Client Meeting",
            "start_time": "2025-03-01T09:00",
            "end_time": "2025-03-01T10:00",
            "priority": 1,
            "status": "CONFIRMED"
        }
    ],
    "conflicts": []
}
```

**Agent Response**:  
"I've rescheduled your apartment tour to 2:00 PM tomorrow and confirmed your important client meeting for 9:00 AM. Both appointments are now set."

---

### 3. Propose n Available Time Slots
**Scenario**:  
Agent needs to find multiple available time slots for a meeting

**User Input**:  
"Find me 3 available 1-hour slots for a client meeting next week between 9am and 5pm"

**Tool Calls**:
```python
find_available_slots(
    calendar_id=1,
    start_date="2025-03-03",
    end_date="2025-03-07",
    duration=60,
    time_range=("09:00", "17:00"),
    max_results=3
)
```

**Tool Response**:
```json
{
    "available_slots": [
        {"start": "2025-03-03T10:00", "end": "2025-03-03T11:00"},
        {"start": "2025-03-05T14:00", "end": "2025-03-05T15:00"},
        {"start": "2025-03-07T09:00", "end": "2025-03-07T10:00"}
    ]
}
```

**Agent Response**:  
"I found 3 available time slots for your client meeting next week:
1. Monday, March 3rd at 10:00 AM
2. Wednesday, March 5th at 2:00 PM
3. Friday, March 7th at 9:00 AM
Which one would you prefer?"

---

### 4. Identify Underutilized Days
**Scenario**:  
Agent wants to identify days with too much free time to schedule additional work

**User Input**:  
"Which day next week is least busy so I can schedule some prospecting calls?"

**Tool Calls**:
```python
check_day_availability(
    calendar_id=1,
    start_date="2025-03-03",
    end_date="2025-03-07",
    time_range=("09:00", "17:00"),
)
```

**Tool Response**:
```json
{
    "underutilized_days": [
        {
            "date": "2025-03-05",
            "free_hours": 6.5,
            "largest_block": {
                "start": "2025-03-05T10:30",
                "end": "2025-03-05T17:00"
            },
            "appointment_count": 1
        },
        {
            "date": "2025-03-07",
            "free_hours": 5.0,
            "largest_block": {
                "start": "2025-03-07T12:00",
                "end": "2025-03-07T17:00"
            },
            "appointment_count": 3
        }
    ],
    "busiest_day": {
        "date": "2025-03-04",
        "free_hours": 1.5,
        "appointment_count": 6
    },
    "recommendation": "2025-03-05"
}
```

**Agent Response**:  
"Based on your schedule for next week, Wednesday (March 5th) is your least busy day with 6.5 hours of free time. You have a large block available from 10:30 AM to 5:00 PM that would be perfect for scheduling prospecting calls. Friday (March 7th) is your second most open day with 5 hours available, including a continuous block from noon to 5:00 PM. Would you like me to block some time on Wednesday for your prospecting calls?"

## Extended Use Cases
