# Calendar Agent Demo

A demo project for an AI-powered calendar management system that helps real estate agents manage their schedules efficiently.

## Setup

1. Clone the repository:
```bash
git clone https://github.com/yourusername/calendar-agent-demo.git
cd calendar-agent-demo
```

2. Install dependencies using Poetry:
```bash
poetry install
```

3. Configure environment:

First, copy the example configuration files:
```bash
cp .env.example .env
cp .env.secrets.example .env.secrets
```

Edit `.env` for application settings:
```env
# Logging Configuration
LOG_LEVEL=INFO  # DEBUG, INFO, WARNING, ERROR, CRITICAL
```

Edit `.env.secrets` for sensitive information:
```env
# OpenAI API Configuration
OPENAI_API_KEY=your_api_key_here
```

If you don't set up an API key, the system will run in test mode using mock responses. This is useful for development and testing, but won't provide real AI interactions.


## Running the Demo

Start the chat interface:
```bash
poetry run python -m calendar_agent.main
```

The system will indicate whether it's using the real GPT-4 model or running in test mode. All interactions are logged to:
- Console: Only warnings and errors for cleaner output
- Local file: `logs/calendar_agent.log` (detailed debug information)
- Logfire dashboard (if configured)


## Real Estate Agent User Stories

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
"Scheduled: Condo Viewing at 123 Main St for Sun Mar 2nd 2:00-3:00 PM (Priority 3). No conflicts detected."

---

### 2. Priority Conflict Resolution
**Scenario**:  
Agent Lisa needs to schedule a $5M luxury home viewing conflicting with existing appointments

**User Input**:  
"Need to show 456 Luxury Lane today 3-5pm. This is high priority!"

**Tool Calls**:
```python
find_optimal_slots(
    start_time="2025-03-01T15:00",
    end_time="2025-03-01T17:00",
    duration=120,
    allow_override_priority_lower_than=2
)
```

**Tool Response**:
```json
{
    "recommended_slots": [
        {
            "type": "override",
            "start": "15:00",
            "end": "17:00",
            "conflicts": [
                {"id": 102, "title": "Apartment Tour", "priority": 3}
            ]
        }
    ]
}
```

**Agent Response**:  
"Available slot found by overriding lower-priority appointments. Confirm scheduling Luxury Home Viewing at 3-5pm? This will reschedule 1 existing appointment."

---

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

### 4. Flexible Duration Adjustment
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


## Tool Architecture

### Base Tools Layer

#### `check_availability`
**Purpose**: Check time slot availability
**Input**:
- start_time: datetime
- end_time: datetime

#### `schedule_appointment`
**Purpose**: Create new appointment with conflict detection  
**Input**:
- time: datetime  
- duration: minutes  
- title: string  
- priority: int (1-5)  

**Output**:
```python
class ScheduleResponse:
    success: bool
    created_appointment: Optional[Appointment]
    conflicts: List[Appointment]
    message: str
```

#### `reschedule_appointment`
**Purpose**: Move existing appointment  
**Input**:
- appointment_id: UUID
- new_time: datetime

#### `cancel_appointment`
**Purpose**: Remove existing appointment
**Input**:
- appointment_id: UUID

### Advanced Tools Layer

#### `smart_schedule`
**Enhanced Logic**:
1. Attempt to move conflicting appointments first
2. Cancel low-priority conflicts if rescheduling fails
3. Create new appointment

**Output Structure**:
```python
class SmartScheduleResponse:
    created_appointment: Appointment
    moved_appointments: List[Appointment]  # Successfully rescheduled
    canceled_appointments: List[Appointment]  # Removed conflicts
    remaining_conflicts: List[Appointment]  # Unresolvable conflicts
```

### Advanced Tools Layer (Scenario Combinations)

#### `find_optimal_slots`
**Purpose**: Find best available time slots with override logic
**Input**:
- time_range: (start: datetime, end: datetime)
- duration: int
- allow_override_priority_lower_than: int
- max_results: int
**Output**:
```python
[
    {
        "type": "free",
        "start": datetime,
        "end": datetime
    },
    {
        "type": "override",
        "start": datetime,
        "end": datetime,
        "conflicts": [
            {
                "id": int,
                "title": str,
                "priority": int
            }
        ]
    }
]
```

#### `smart_schedule`  
**Purpose**: Intelligent scheduling with auto-conflict resolution
**Input**:
- title: str
- desired_time: datetime
- duration: int
- priority: int
**Output**:
```python
{
    "scheduled": bool,
    "method": Literal["direct", "override"],
    "appointment": Appointment,
    "cancelled_appointments": List[int]
}
```

### Auxiliary Tools Layer

#### `get_calendar_overview`
**Purpose**: Get calendar summary
**Input**:
- date_range: (start: date, end: date)
**Output**:
```python
{
    "busy_hours": float,
    "high_priority_slots": List[TimeSlot],
    "override_opportunities": List[OverrideSlot]
}
```

#### `reschedule_low_priority`
**Purpose**: Reschedule lower priority appointments
**Input**:
- target_window: (start: datetime, end: datetime)
- min_priority: int
**Output**:
```python
{
    "rescheduled": int,
    "freed_slots": List[TimeSlot],
    "failed_reschedules": List[int]
}
```
