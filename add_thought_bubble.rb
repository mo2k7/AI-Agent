require 'xcodeproj'

project_path = 'ui/AIAgent.xcodeproj'
project = Xcodeproj::Project.open(project_path)

# Correct target names
target_macos = project.targets.find { |t| t.name == 'AIAgentApp' }
target_ios = project.targets.find { |t| t.name == 'AIAgentiOS' }

if target_macos.nil? || target_ios.nil?
    puts "Error: Could not find one or both targets."
    exit 1
end

# Find the DocumentViewer group
ui_group = project.main_group.find_subpath(File.join('AIAgentUI', 'Views'), true)
doc_viewer_group = ui_group.find_subpath('DocumentViewer', true)
doc_viewer_group.set_source_tree('<group>')
doc_viewer_group.set_path('DocumentViewer')

# Add the ThoughtBubbleView file reference
file_path = 'ThoughtBubbleView.swift'
file_ref = doc_viewer_group.files.find { |f| f.path == file_path }
if file_ref
    puts "ThoughtBubbleView.swift already exists in group."
else
    file_ref = doc_viewer_group.new_file(file_path)
    file_ref.set_source_tree('<group>') # Important for correct path resolution
    puts "Added ThoughtBubbleView.swift to group."
end

# Ensure it's in the compile sources phase for both targets
[target_macos, target_ios].each do |target|
    build_phase = target.source_build_phase
    unless build_phase.files.any? { |f| f.file_ref == file_ref }
        build_file = build_phase.add_file_reference(file_ref)
        puts "Added ThoughtBubbleView.swift to target #{target.name}"
    else
        puts "ThoughtBubbleView.swift already in target #{target.name}"
    end
end

project.save
puts "Project saved successfully."
