# Whenever - Duel Links Tournament Cog

A Red-Bot cog for managing Yu-Gi-Oh! Duel Links tournaments.

## Installation

```bash
[p]repo add cobray-cogs https://github.com/alsaiduq-lab/cobray-cogs
[p]cog install cobray-cogs whenever
[p]load whenever
```

## Setup

1. Set tournament role:

```
[p]whenever setrole @role
```

2. Set tournament and announcement channels:

```
[p]whenever setchannel #tournament-channel
[p]whenever setannouncements #tournament-announcements
```

3. Configure tournament settings:

```
[p]whenever config deck_check_required true
[p]whenever config send_reminders true
```

4. (Optional) Set up match scheduling and reminders:

```
[p]whenever config reminder_minutes 15
```

## Usage

### Tournament Administration

```
[p]whenever create "Tournament Name" single_elimination 3  # Create a single elimination Bo3 tournament
[p]whenever open                                           # Open registration
[p]whenever close                                          # Close registration
[p]whenever start                                          # Start the tournament
```

### Player Commands

```
[p]whenever register                                       # Register for a tournament
[p]whenever schedule @opponent tomorrow at 8pm             # Schedule a match
[p]whenever report @opponent 2 1                           # Report a 2-1 match win
[p]whenever bracket                                        # View the current bracket
[p]whenever upcoming                                       # See upcoming scheduled matches
[p]whenever stats                                          # View tournament statistics
```

For a full list of commands, type `[p]help whenever`

## Requirements

- Red-Bot V3
- discord.py 2.0+
- dateparser (for match scheduling)
- Manage Server permission

## Support

For issues and suggestions, open an issue on GitHub or contact the developer.

## Features

- Multiple tournament formats: single elimination, double elimination, Swiss, and round robin
- Match scheduling with automatic reminders
- Private channels/threads for tournament participants
- Tournament announcements in dedicated channel
- Tournament statistics and standings
- Match reporting with optional confirmation
- Deck submission and verification
- Bracket visualization for all tournament formats

## Areas for Improvement
- Tournament bracket visualization could be enhanced with images/graphics
- Guild-specific tournament instances (currently one active tournament per guild)
- Customizable tournament themes and branding
- Integration with other Discord bots for additional features
- Web dashboard for more advanced tournament management