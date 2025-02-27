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
