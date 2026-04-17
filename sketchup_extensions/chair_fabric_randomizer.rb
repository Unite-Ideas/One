# frozen_string_literal: true

# Chair Fabric Randomizer
# SketchUp 2024+ (Ruby 3.x)

module ChurchTools
  module ChairFabricRandomizer
    extend self

    PLUGIN_NAME = 'Chair Fabric Randomizer'

    def run
      model = Sketchup.active_model
      selection = model.selection

      unless model.active_path && !model.active_path.empty?
        UI.messagebox('Open one chair for editing first, then select the seat/back groups or components to target.')
        return
      end

      selected_targets = selection.grep(Sketchup::Group) + selection.grep(Sketchup::ComponentInstance)
      if selected_targets.empty?
        UI.messagebox('Select at least one Group or ComponentInstance inside the opened chair.')
        return
      end

      chair_root = detect_chair_root(model.active_path)
      unless chair_root
        UI.messagebox('Could not detect the chair root in the active editing path.')
        return
      end

      source_materials = collect_source_materials(selected_targets)
      if source_materials.empty?
        UI.messagebox('No materials found on selected targets. Paint the sample seat/back first, then run again.')
        return
      end

      palette = prompt_for_palette(model)
      return unless palette

      exemplar_chair_def = chair_root.definition
      chair_instances = exemplar_chair_def.instances

      if chair_instances.size <= 1
        UI.messagebox('Only one chair instance found. Duplicate the chair first, then run the tool again.')
        return
      end

      chain_prefix = build_chain_prefix(model.active_path, chair_root)
      target_chains = selected_targets.map { |target| chain_prefix + [descriptor_for(target)] }

      model.start_operation(PLUGIN_NAME, true)
      changed = 0

      begin
        chair_instances.each do |chair_instance|
          next if chair_instance.deleted?

          chair_instance.make_unique

          target_chains.each do |chain|
            target = resolve_chain(chair_instance, chain)
            next unless target

            random_material = palette.sample
            recolor_target_instance(target, source_materials, random_material)
            changed += 1
          end
        end
      rescue StandardError => e
        model.abort_operation
        UI.messagebox("#{PLUGIN_NAME} failed: #{e.message}")
        raise e
      end

      model.commit_operation
      UI.messagebox("Updated #{changed} target part(s) across #{chair_instances.size} chair instance(s).")
    end

    private

    def detect_chair_root(active_path)
      return nil if active_path.empty?

      named = active_path.find do |inst|
        n = [safe_name(inst), safe_def_name(inst)].join(' ').downcase
        n.include?('chair')
      end

      named || active_path.first
    end

    def safe_name(instance)
      instance.respond_to?(:name) ? instance.name.to_s : ''
    end

    def safe_def_name(instance)
      instance.respond_to?(:definition) ? instance.definition.name.to_s : ''
    end

    def build_chain_prefix(active_path, chair_root)
      idx = active_path.index(chair_root)
      return [] unless idx

      # From the object right below chair_root to current open container.
      active_path[(idx + 1)..].to_a.map { |inst| descriptor_for(inst) }
    end

    def descriptor_for(instance)
      parent_entities = instance.parent
      sibling_instances = parent_entities.grep(Sketchup::Group) + parent_entities.grep(Sketchup::ComponentInstance)
      sibling_index = sibling_instances.index(instance)

      {
        def_name: safe_def_name(instance),
        name: safe_name(instance),
        sibling_index: sibling_index
      }
    end

    def resolve_chain(chair_instance, chain)
      parent = chair_instance

      chain.each do |step|
        entities = parent.definition.entities
        siblings = entities.grep(Sketchup::Group) + entities.grep(Sketchup::ComponentInstance)

        candidate = siblings.find do |inst|
          safe_def_name(inst) == step[:def_name] && safe_name(inst) == step[:name]
        end

        candidate ||= siblings[step[:sibling_index]] if step[:sibling_index]
        return nil unless candidate

        parent = candidate
      end

      parent
    end

    def collect_source_materials(instances)
      mats = []
      instances.each do |inst|
        mats << inst.material if inst.material
        gather_face_materials(inst.definition.entities, mats)
      end
      mats.compact.uniq
    end

    def gather_face_materials(entities, out)
      entities.grep(Sketchup::Face).each do |face|
        out << face.material if face.material
        out << face.back_material if face.back_material
      end

      nested = entities.grep(Sketchup::Group) + entities.grep(Sketchup::ComponentInstance)
      nested.each { |inst| gather_face_materials(inst.definition.entities, out) }
    end

    def prompt_for_palette(model)
      names = model.materials.map(&:name).sort
      default = names.first(4).join(', ')
      prompts = ['Material names (comma separated, 2+):']
      values = [default]
      input = UI.inputbox(prompts, values, 'Choose random fabric palette')
      return nil unless input

      requested = input.first.to_s.split(',').map(&:strip).reject(&:empty?)
      if requested.size < 2
        UI.messagebox('Provide at least 2 material names.')
        return nil
      end

      palette = requested.map { |name| model.materials[name] }.compact.uniq
      if palette.size < 2
        UI.messagebox('At least 2 valid model materials are required.')
        return nil
      end

      palette
    end

    def recolor_target_instance(instance, source_materials, new_material)
      instance.make_unique
      instance.material = new_material if source_materials.include?(instance.material)
      replace_materials(instance.definition.entities, source_materials, new_material)
    end

    def replace_materials(entities, source_materials, new_material)
      entities.grep(Sketchup::Face).each do |face|
        face.material = new_material if source_materials.include?(face.material)
        face.back_material = new_material if source_materials.include?(face.back_material)
      end

      nested = entities.grep(Sketchup::Group) + entities.grep(Sketchup::ComponentInstance)
      nested.each do |inst|
        inst.material = new_material if source_materials.include?(inst.material)
        replace_materials(inst.definition.entities, source_materials, new_material)
      end
    end

    unless file_loaded?(__FILE__)
      UI.menu('Extensions').add_item(PLUGIN_NAME) { run }
      file_loaded(__FILE__)
    end
  end
end
