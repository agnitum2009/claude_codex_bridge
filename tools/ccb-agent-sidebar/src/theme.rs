use std::env;

use ratatui::prelude::{Color, Modifier, Style};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct SidebarTheme {
    pub name: &'static str,
    pub focus: Color,
    pub selection_fg: Color,
    pub selection_bg: Option<Color>,
    pub success: Color,
    pub warning: Color,
    pub danger: Color,
    pub info: Color,
    pub neutral: Color,
    pub muted: Color,
    pub clear: Color,
    pub scrollbar_track: Color,
    pub scrollbar_thumb: Color,
}

impl SidebarTheme {
    pub fn from_profile(profile: &str) -> Self {
        match normalize_profile(profile).as_deref() {
            Some("light") => Self::light(),
            _ => Self::default_dark(),
        }
    }

    pub fn from_env() -> Self {
        let profile = env::var("CCB_SIDEBAR_THEME_PROFILE")
            .ok()
            .filter(|value| !value.trim().is_empty())
            .or_else(|| env::var("CCB_TMUX_THEME_PROFILE").ok());
        profile
            .as_deref()
            .map(Self::from_profile)
            .unwrap_or_else(Self::default_dark)
    }

    pub fn default_dark() -> Self {
        Self {
            name: "default",
            focus: Color::DarkGray,
            selection_fg: Color::Reset,
            selection_bg: None,
            success: Color::Green,
            warning: Color::Yellow,
            danger: Color::Red,
            info: Color::Blue,
            neutral: Color::Gray,
            muted: Color::DarkGray,
            clear: Color::Cyan,
            scrollbar_track: Color::DarkGray,
            scrollbar_thumb: Color::Gray,
        }
    }

    pub fn light() -> Self {
        Self {
            name: "light",
            focus: Color::Rgb(108, 111, 133),
            selection_fg: Color::Rgb(76, 79, 105),
            selection_bg: Some(Color::Rgb(204, 208, 218)),
            success: Color::Rgb(64, 160, 43),
            warning: Color::Rgb(223, 142, 29),
            danger: Color::Rgb(210, 15, 57),
            info: Color::Rgb(30, 102, 245),
            neutral: Color::Rgb(108, 111, 133),
            muted: Color::Rgb(156, 160, 176),
            clear: Color::Rgb(23, 146, 153),
            scrollbar_track: Color::Rgb(220, 224, 232),
            scrollbar_thumb: Color::Rgb(156, 160, 176),
        }
    }

    pub fn selection_style(self) -> Style {
        let base = Style::default()
            .fg(self.selection_fg)
            .add_modifier(Modifier::BOLD);
        if let Some(bg) = self.selection_bg {
            base.bg(bg)
        } else {
            Style::default().add_modifier(Modifier::REVERSED)
        }
    }
}

pub fn normalize_profile(profile: &str) -> Option<String> {
    let value = profile.trim().to_ascii_lowercase();
    match value.as_str() {
        "default" | "dark" | "contrast" | "light" => Some(value),
        _ => None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn maps_light_profile_to_light_theme() {
        let theme = SidebarTheme::from_profile(" light ");

        assert_eq!(theme.name, "light");
        assert_eq!(theme.focus, Color::Rgb(108, 111, 133));
        assert_eq!(theme.selection_bg, Some(Color::Rgb(204, 208, 218)));
    }

    #[test]
    fn unknown_profile_falls_back_to_default_dark() {
        let theme = SidebarTheme::from_profile("unknown");

        assert_eq!(theme.name, "default");
        assert_eq!(theme.focus, Color::DarkGray);
    }
}
