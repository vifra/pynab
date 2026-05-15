COLOR_GROUPS = [
    ("Red", ["#ff0000", "#fa8072"]),
    ("Orange", ["#ff4500", "#ffa500"]),
    ("Yellow", ["#fff200"]),
    ("Green", ["#006633", "#90ee90"]),
    ("Blue", ["#0003ff", "#00ffff"]),
    ("Purple", ["#5f00ff", "#4b0082"]),
    ("Pink", ["#ff00df", "#dda0dd"]),
    ("Neutral", ["#ffffff", "#000000"]),
]


def choreography_color_palettes():
    return [
        {
            "name": group_name,
            "colors": [
                {
                    "value": value,
                    "label": f"{group_name} {color_index + 1}",
                }
                for color_index, value in enumerate(colors)
            ],
        }
        for group_name, colors in COLOR_GROUPS
    ]


def choreography_color_values():
    return {
        color["value"]
        for palette in choreography_color_palettes()
        for color in palette["colors"]
    }
