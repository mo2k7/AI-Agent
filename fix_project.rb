require 'xcodeproj'
project_path = '/Users/muhammadabdullah/AI Automation Agent macOS/ui/AIAgent.xcodeproj'
project = Xcodeproj::Project.open(project_path)
targets = project.targets.select { |t| ['AIAgentApp', 'AIAgentiOS'].include?(t.name) }

['SiriMeshAnimationView.swift', 'DocumentChatOverlay.swift', 'EnhancedDocumentPreviewer.swift', 'DocumentViewerModal.swift'].each do |name|
  project.files.select { |f| f.path && f.path.include?(name) }.each(&:remove_from_project)
end

views_group = project.main_group.find_subpath(File.join('AIAgentUI', 'Views'), false)
if views_group
  doc_group = views_group.children.find { |g| g.display_name == 'DocumentViewer' || g.path == 'DocumentViewer' }
  unless doc_group
    doc_group = views_group.new_group('DocumentViewer', 'DocumentViewer')
  end
  
  files_to_add = [
    'SiriMeshAnimationView.swift',
    'DocumentChatOverlay.swift',
    'EnhancedDocumentPreviewer.swift',
    'DocumentViewerModal.swift'
  ]
  
  files_to_add.each do |file_name|
    # explicitly define source tree and path relative to source root
    file_ref = doc_group.new_file("AIAgentUI/Views/DocumentViewer/#{file_name}")
    file_ref.source_tree = 'SOURCE_ROOT'
    
    targets.each do |target|
      target.add_file_references([file_ref])
      puts "Added #{file_name} mapped explicitly to SOURCE_ROOT for target #{target.name}"
    end
  end
end

project.save
puts "Successfully saved project.pbxproj with SOURCE_ROOT explicitly defined paths."
