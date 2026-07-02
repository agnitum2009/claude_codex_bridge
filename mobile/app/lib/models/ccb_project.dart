class CcbProject {
  const CcbProject({
    required this.id,
    required this.displayName,
    required this.root,
    this.favorite = false,
    this.health = 'unknown',
    this.hasWorkingAgents = false,
    this.workingAgentCount = 0,
  });

  final String id;
  final String displayName;
  final String root;
  final bool favorite;
  final String health;
  final bool hasWorkingAgents;
  final int workingAgentCount;

  factory CcbProject.fromJson(Map<String, Object?> json) {
    final workingAgentCount =
        _optionalInt(json['working_agent_count']) ??
        _optionalInt(json['active_agent_count']) ??
        0;
    return CcbProject(
      id: _text(json['id']),
      displayName: _text(json['display_name'], fallback: _text(json['id'])),
      root: _text(json['root']),
      favorite: json['favorite'] == true,
      health: _text(json['health'], fallback: 'unknown'),
      hasWorkingAgents:
          json['has_working_agents'] == true ||
          json['has_active_agents'] == true ||
          workingAgentCount > 0,
      workingAgentCount: workingAgentCount,
    );
  }
}

String _text(Object? value, {String fallback = ''}) {
  final text = (value ?? '').toString().trim();
  return text.isEmpty ? fallback : text;
}

int? _optionalInt(Object? value) => int.tryParse((value ?? '').toString());
