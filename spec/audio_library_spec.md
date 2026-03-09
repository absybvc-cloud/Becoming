# Audio Library Specification

The sound library defines the sonic identity of Becoming.

## Categories

rhythm  
drone  
tonal  
field  
noise

## Recommended MVP Size

rhythm: 20–30  
drone: 30–40  
tonal: 25–35  
field: 20–30  
noise: 15–20  

## Metadata Fields

id  
category  
file_path  
duration  
energy_level  
density_level  
loopable  
cooldown  
tags

Example:

{
"id": "drone_01",
"category": "drone",
"duration": 20,
"loopable": true,
"energy_level": 3,
"cooldown": 120
}