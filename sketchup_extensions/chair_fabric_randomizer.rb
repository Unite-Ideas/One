# frozen_string_literal: true

# Chair Fabric Randomizer
# SketchUp 2024+ (Ruby 3.x)

require 'json'

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

      colors = prompt_for_color_palette
      return unless colors

      tinted_by_source = build_tinted_materials(model, source_materials, colors)
      if tinted_by_source.empty?
        UI.messagebox('Could not build tinted materials from your selected colors.')
        return
      end

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

            color_index = rand(colors.length)
            recolor_target_instance(target, source_materials, tinted_by_source, color_index)
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

    def prompt_for_color_palette
      return fallback_palette_prompt unless defined?(UI::HtmlDialog)

      dialog = UI::HtmlDialog.new(
        dialog_title: 'Choose Random Fabric Palette',
        preferences_key: 'ChairFabricRandomizerPalette',
        scrollable: true,
        resizable: false,
        width: 430,
        height: 380,
        style: UI::HtmlDialog::STYLE_DIALOG
      )

      html = <<~HTML
        <!doctype html>
        <html>
        <head>
          <meta charset="UTF-8" />
          <style>
            body { font-family: Arial, sans-serif; margin: 14px; }
            h3 { margin: 0 0 10px; }
            .count { display: flex; gap: 10px; margin-bottom: 12px; }
            .color-row { margin: 8px 0; display: flex; align-items: center; gap: 10px; }
            button { margin-top: 14px; padding: 8px 12px; }
          </style>
        </head>
        <body>
          <h3>Choose random fabric colors</h3>
          <div class="count">
            <label><input type="radio" name="count" value="2" checked> 2 colors</label>
            <label><input type="radio" name="count" value="3"> 3 colors</label>
            <label><input type="radio" name="count" value="4"> 4 colors</label>
          </div>

          <div id="colors"></div>

          <button onclick="submitColors()">Apply</button>
          <button onclick="sketchup.cancel()" style="margin-left:8px;">Cancel</button>

          <script>
            const defaults = ['#8d3f3f', '#3f5f8d', '#5c7a52', '#6f4f8e'];

            function selectedCount() {
              return parseInt(document.querySelector('input[name="count"]:checked').value, 10);
            }

            function renderPickers() {
              const count = selectedCount();
              const holder = document.getElementById('colors');
              holder.innerHTML = '';

              for (let i = 0; i < count; i++) {
                const row = document.createElement('div');
                row.className = 'color-row';
                row.innerHTML = `<label>Color ${i + 1}</label><input type="color" value="${defaults[i]}">`;
                holder.appendChild(row);
              }
            }

            function submitColors() {
              const picks = Array.from(document.querySelectorAll('#colors input[type="color"]')).map(i => i.value);
              sketchup.apply(JSON.stringify(picks));
            }

            document.querySelectorAll('input[name="count"]').forEach(r => r.addEventListener('change', renderPickers));
            renderPickers();
          </script>
        </body>
        </html>
      HTML

      result = nil
      dialog.add_action_callback('apply') do |_ctx, json|
        begin
          arr = JSON.parse(json)
          result = arr.map { |hex| hex_to_color(hex) }.compact.uniq
        rescue StandardError
          result = nil
        end
        dialog.close
      end

      dialog.add_action_callback('cancel') do |_ctx|
        result = nil
        dialog.close
      end

      dialog.set_html(html)
      dialog.show_modal

      return nil if result.nil? || result.size < 2

      result
    end

    def fallback_palette_prompt
      prompts = ['Number of colors (2-4):', 'Hex colors comma-separated (#ff0000,#00ff00):']
      values = ['2', '#8d3f3f, #3f5f8d']
      input = UI.inputbox(prompts, values, 'Choose random fabric colors')
      return nil unless input

      count = input[0].to_i
      return nil unless (2..4).include?(count)

      colors = input[1].to_s.split(',').map { |hex| hex_to_color(hex) }.compact.uniq
      return nil if colors.size < count

      colors.first(count)
    end

    def hex_to_color(hex)
      h = hex.to_s.strip
      h = "##{h}" unless h.start_with?('#')
      return nil unless h.match?(/^#[0-9a-fA-F]{6}$/)

      r = h[1..2].to_i(16)
      g = h[3..4].to_i(16)
      b = h[5..6].to_i(16)
      Sketchup::Color.new(r, g, b)
    end

    def build_tinted_materials(model, source_materials, colors)
      by_source = {}

      source_materials.each do |source|
        variants = colors.map.with_index do |color, idx|
          find_or_create_tinted_material(model, source, color, idx)
        end.compact

        by_source[source] = variants if variants.any?
      end

      by_source
    end

    def find_or_create_tinted_material(model, source, color, idx)
      hex = format('%02X%02X%02X', color.red, color.green, color.blue)
      base = source.display_name.to_s.strip
      base = 'Fabric' if base.empty?
      safe = base.gsub(/[^0-9A-Za-z_\-]/, '_')
      name = "CFR_#{safe}_#{idx + 1}_#{hex}"

      existing = model.materials[name]
      return existing if existing

      mat = model.materials.add(name)
      mat.alpha = source.alpha if source.respond_to?(:alpha)

      if source.texture && source.texture.filename
        mat.texture = source.texture.filename
        mat.texture.size = source.texture.size if mat.texture && source.texture.respond_to?(:size)
      end

      mat.color = color
      mat
    rescue StandardError
      nil
    end

    def recolor_target_instance(instance, source_materials, tinted_by_source, color_index)
      instance.make_unique
      if source_materials.include?(instance.material)
        replacement = tinted_by_source[instance.material]
        instance.material = replacement[color_index] if replacement && replacement[color_index]
      end
      replace_materials(instance.definition.entities, source_materials, tinted_by_source, color_index)
    end

    def replace_materials(entities, source_materials, tinted_by_source, color_index)
      entities.grep(Sketchup::Face).each do |face|
        if source_materials.include?(face.material)
          replacement = tinted_by_source[face.material]
          face.material = replacement[color_index] if replacement && replacement[color_index]
        end

        if source_materials.include?(face.back_material)
          replacement = tinted_by_source[face.back_material]
          face.back_material = replacement[color_index] if replacement && replacement[color_index]
        end
      end

      nested = entities.grep(Sketchup::Group) + entities.grep(Sketchup::ComponentInstance)
      nested.each do |inst|
        if source_materials.include?(inst.material)
          replacement = tinted_by_source[inst.material]
          inst.material = replacement[color_index] if replacement && replacement[color_index]
        end
        replace_materials(inst.definition.entities, source_materials, tinted_by_source, color_index)
      end
    end

    unless file_loaded?(__FILE__)
      UI.menu('Extensions').add_item(PLUGIN_NAME) { run }
      file_loaded(__FILE__)
    end
  end
end
