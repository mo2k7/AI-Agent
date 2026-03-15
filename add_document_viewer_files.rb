require 'xcodeproj'

project_path = '/Users/muhammadabdullah/AI Automation Agent macOS/ui/AIAgent.xcodeproj'
project = Xcodeproj::Project.open(project_path)

targets = project.targets.select { |t| ['AIAgentApp', 'AIAgentiOS'].include?(t.name) }

# Navigation to the Views/DocumentViewer group
# Using group relative paths
ui_group = project.main_group.find_subpath(File.join('AIAgentUI', 'Views', 'DocumentViewer'), true)
ui_group.set_source_tree('<group>')

# The paths relative to AIAgentUI group
files_to_add = [
  'AIAgentUI/Views/DocumentViewer/SiriMeshAnimationView.swift',
  'AIAgentUI/Views/DocumentViewer/DocumentChatOverlay.swift',
  'AIAgentUI/Views/DocumentViewer/EnhancedDocumentPreviewer.swift',
  'AIAgentUI/Views/DocumentViewer/DocumentViewerModal.swift'
]

files_to_add.each do |file_path|
  file_name = file_path.split('/').last
  existing = ui_group.files.find { |f| f.path == file_name }
  file_ref = existing || ui_group.new_file(file_path)
  
  targets.each do |target|
    unless target.source_build_phase.files_references.include?(file_ref)
      target.add_file_references([file_ref])
      puts "Added #{file_name} to target #{target.name}"
    end
  end
end

project.save
puts "Successfully saved project.pbxproj with new files."
