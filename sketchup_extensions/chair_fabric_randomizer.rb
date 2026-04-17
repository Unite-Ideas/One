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
        UI.messagebox('Open one chair for editing first, then select one labeled target part (example: SEAT BACK).')
        return
      end

      selected_targets = selection.grep(Sketchup::Group) + selection.grep(Sketchup::ComponentInstance)
      if selected_targets.empty?
        UI.messagebox('Select at least one labeled Group or ComponentInstance inside the opened chair.')
        return
      end

      chair_root = detect_chair_root(model.active_path)
      unless chair_root
        UI.messagebox('Could not detect the chair root in the active editing path.')
        return
      end

      source_materials = collect_source_materials(selected_targets)
      if source_materials.empty?
        UI.messagebox('No materials found on selected targets. Paint the sample SEAT BACK/SEAT BOTTOM first, then run again.')
        return
      end

      selected_labels = collect_target_labels(selected_targets)
      settings = prompt_for_settings
      return unless settings

      target_labels = if settings[:target_mode] == 'both'
                        ['SEAT BACK', 'SEAT BOTTOM']
                      else
                        labels = selected_labels
                        labels = prompt_for_target_labels if labels.empty?
                        labels
                      end
      return if target_labels.empty?

      chair_instances = find_candidate_chair_instances(model, chair_root, target_labels)
      if chair_instances.empty?
        UI.messagebox('No chair instances were found with matching target labels. Check your part labels (example: SEAT BACK).')
        return
      end

      variants = build_variant_materials(model, source_materials, settings[:colors], settings[:material_mode])
      if variants.empty?
        UI.messagebox('Could not build material variants from your settings.')
        return
      end

      debug_log(model, chair_root, target_labels, chair_instances, settings)
      debug_variant_summary(variants, settings[:colors].size)

      color_plan = build_color_plan(chair_instances.size, settings[:colors].size)

      model.start_operation(PLUGIN_NAME, true)
      changed = 0
      color_usage = Hash.new(0)

      begin
        chair_instances.each_with_index do |chair_instance, i|
          next if chair_instance.deleted?

          chair_instance.make_unique
          targets = find_labeled_targets(chair_instance.definition.entities, target_labels)
          next if targets.empty?

          color_index = color_plan[i]
          color_usage[color_index] += 1
          targets.each do |target|
            chosen_variant = variants[color_index % variants.length]
            recolor_target_instance(target, source_materials, chosen_variant)
            changed += 1
          end
        end
      rescue StandardError => e
        model.abort_operation
        UI.messagebox("#{PLUGIN_NAME} failed: #{e.message}")
        raise e
      end

      model.commit_operation
      debug_color_usage(settings[:colors], color_usage)
      UI.messagebox("Updated #{changed} labeled target part(s) across #{chair_instances.size} chair instance(s).")
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

    def collect_target_labels(instances)
      labels = instances.map do |inst|
        name = safe_name(inst).strip
        name.empty? ? safe_def_name(inst).strip : name
      end
      labels.map(&:upcase).reject(&:empty?).uniq
    end

    def prompt_for_target_labels
      input = UI.inputbox(
        ['Target part label(s), comma-separated (example: SEAT BACK, SEAT BOTTOM):'],
        ['SEAT BACK'],
        'Chair part labels'
      )
      return [] unless input

      input.first.to_s.split(',').map { |s| s.strip.upcase }.reject(&:empty?).uniq
    end

    def find_labeled_targets(entities, target_labels, out = [])
      items = entities.grep(Sketchup::Group) + entities.grep(Sketchup::ComponentInstance)
      items.each do |inst|
        nm = safe_name(inst).strip.upcase
        dn = safe_def_name(inst).strip.upcase

        out << inst if target_labels.include?(nm) || target_labels.include?(dn)

        find_labeled_targets(inst.definition.entities, target_labels, out)
      end
      out
    end

    def find_candidate_chair_instances(model, chair_root, target_labels)
      all = all_instances_in_entities(model.entities)

      by_name_and_label = all.select do |inst|
        chairish = [safe_name(inst), safe_def_name(inst)].join(' ').downcase.include?('chair')
        chairish && contains_target_label?(inst.definition.entities, target_labels)
      end

      return by_name_and_label.uniq unless by_name_and_label.empty?

      by_label_only = all.select { |inst| contains_target_label?(inst.definition.entities, target_labels) }
      return by_label_only.uniq unless by_label_only.empty?

      [chair_root]
    end

    def all_instances_in_entities(entities, out = [])
      items = entities.grep(Sketchup::Group) + entities.grep(Sketchup::ComponentInstance)
      items.each do |inst|
        out << inst
        all_instances_in_entities(inst.definition.entities, out)
      end
      out
    end

    def contains_target_label?(entities, target_labels)
      items = entities.grep(Sketchup::Group) + entities.grep(Sketchup::ComponentInstance)
      items.any? do |inst|
        nm = safe_name(inst).strip.upcase
        dn = safe_def_name(inst).strip.upcase
        target_labels.include?(nm) || target_labels.include?(dn) || contains_target_label?(inst.definition.entities, target_labels)
      end
    end

    def build_color_plan(chair_count, color_count)
      raw = Array.new(chair_count) { |idx| idx % color_count }
      raw.shuffle(random: Random.new)
    end



    def debug_variant_summary(variants, expected_count)
      puts("[#{PLUGIN_NAME}] Variant count generated: #{variants.length}, expected=#{expected_count}")

      variants.each_with_index do |variant, i|
        tex = variant.texture ? 'yes' : 'no'
        mtype = variant.respond_to?(:materialType) ? variant.materialType : 'n/a'
        puts("[#{PLUGIN_NAME}] Variant #{i + 1}: name='#{variant.display_name}', texture=#{tex}, color=#{variant.color}, materialType=#{mtype}")
      end
    end

    def debug_color_usage(colors, color_usage)
      mapped = colors.each_with_index.map do |c, i|
        hex = format('#%02X%02X%02X', c.red, c.green, c.blue)
        "#{hex}=#{color_usage[i] || 0}"
      end
      puts("[#{PLUGIN_NAME}] Color usage by chair: #{mapped.join(', ')}")
    end

    def debug_log(model, chair_root, target_labels, chair_instances, settings)
      puts("[#{PLUGIN_NAME}] Model: #{model.title}")
      puts("[#{PLUGIN_NAME}] Active root: #{safe_name(chair_root)} / #{safe_def_name(chair_root)}")
      puts("[#{PLUGIN_NAME}] Target labels: #{target_labels.join(', ')}")
      puts("[#{PLUGIN_NAME}] Candidate chairs found: #{chair_instances.size}")
      puts("[#{PLUGIN_NAME}] Colors selected: #{settings[:colors].map { |c| format('#%02X%02X%02X', c.red, c.green, c.blue) }.join(', ')}")
      puts("[#{PLUGIN_NAME}] Material mode: #{settings[:material_mode]}")
      puts("[#{PLUGIN_NAME}] Target mode: #{settings[:target_mode]}")
    end

    def prompt_for_settings
      return fallback_settings_prompt unless defined?(UI::HtmlDialog)

      dialog = UI::HtmlDialog.new(
        dialog_title: 'Choose Random Fabric Palette',
        preferences_key: 'ChairFabricRandomizerPalette',
        scrollable: true,
        resizable: false,
        width: 500,
        height: 560,
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
            .section { margin-bottom: 14px; border: 1px solid #ddd; border-radius: 6px; padding: 10px; }
            .count { display: flex; gap: 12px; margin-bottom: 8px; }
            .color-row { margin: 8px 0; display: flex; align-items: center; gap: 10px; }
            .help { color: #555; font-size: 12px; }
            button { margin-top: 12px; padding: 8px 12px; }
          </style>
        </head>
        <body>
          <div class="section">
            <h3>Color count</h3>
            <div class="count">
              <label><input type="radio" name="count" value="2" checked> 2 colors</label>
              <label><input type="radio" name="count" value="3"> 3 colors</label>
              <label><input type="radio" name="count" value="4"> 4 colors</label>
            </div>
            <div id="colors"></div>
          </div>

          <div class="section">
            <h3>Material behavior</h3>
            <label><input type="radio" name="materialMode" value="colorize" checked> Colorize existing texture image</label><br>
            <label><input type="radio" name="materialMode" value="solid"> Replace with solid color (remove texture)</label>
          </div>

          <div class="section">
            <h3>Target behavior</h3>
            <label><input type="radio" name="targetMode" value="selected" checked> Just change selected element label(s)</label><br>
            <label><input type="radio" name="targetMode" value="both"> Apply together to SEAT BACK + SEAT BOTTOM</label>
            <div class="help">When "both" is selected, each chair gets one random color and both parts match each other.</div>
          </div>

          <button onclick="submitSettings()">Apply</button>
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

            function submitSettings() {
              const payload = {
                colors: Array.from(document.querySelectorAll('#colors input[type="color"]')).map(i => i.value),
                material_mode: document.querySelector('input[name="materialMode"]:checked').value,
                target_mode: document.querySelector('input[name="targetMode"]:checked').value
              };
              sketchup.apply(JSON.stringify(payload));
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
          payload = JSON.parse(json)
          result = parse_settings_payload(payload)
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
      result
    end

    def fallback_settings_prompt
      prompts = [
        'Number of colors (2-4):',
        'Hex colors comma-separated (#ff0000,#00ff00):',
        'Material mode (colorize or solid):',
        'Target mode (selected or both):'
      ]
      values = ['2', '#8d3f3f, #3f5f8d', 'colorize', 'selected']
      input = UI.inputbox(prompts, values, 'Choose random fabric settings')
      return nil unless input

      count = input[0].to_i
      return nil unless (2..4).include?(count)

      colors = input[1].to_s.split(',').map { |hex| hex_to_color(hex) }.compact
      colors = colors.uniq
      return nil if colors.size < count

      mode = input[2].to_s.strip.downcase
      mode = 'colorize' unless %w[colorize solid].include?(mode)

      target_mode = input[3].to_s.strip.downcase
      target_mode = 'selected' unless %w[selected both].include?(target_mode)

      {
        colors: colors.first(count),
        material_mode: mode,
        target_mode: target_mode
      }
    end

    def parse_settings_payload(payload)
      colors = Array(payload['colors']).map { |hex| hex_to_color(hex) }.compact.uniq
      return nil if colors.size < 2

      material_mode = payload['material_mode'].to_s
      material_mode = 'colorize' unless %w[colorize solid].include?(material_mode)

      target_mode = payload['target_mode'].to_s
      target_mode = 'selected' unless %w[selected both].include?(target_mode)

      {
        colors: colors,
        material_mode: material_mode,
        target_mode: target_mode
      }
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

    def build_variant_materials(model, source_materials, colors, material_mode)
      base_source = source_materials.first
      return [] unless base_source

      variants = colors.map.with_index do |color, idx|
        find_or_create_variant_material(model, base_source, color, idx, material_mode)
      end.compact

      if variants.length < colors.length
        puts("[#{PLUGIN_NAME}] Warning: base source '#{base_source.display_name}' produced only #{variants.length}/#{colors.length} variants.")
      end

      variants
    end

    def find_or_create_variant_material(model, source, color, idx, material_mode)
      hex = format('%02X%02X%02X', color.red, color.green, color.blue)
      base = source.display_name.to_s.strip
      base = 'Fabric' if base.empty?
      safe = base.gsub(/[^0-9A-Za-z_\-]/, '_')
      name = "CFR_#{material_mode}_#{safe}_#{idx + 1}_#{hex}"

      mat = model.materials[name] || model.materials.add(name)
      mat.alpha = source.alpha if source.respond_to?(:alpha)

      if material_mode == 'colorize' && source.texture
        begin
          copy_texture(source, mat)
          raise 'Texture copy failed.' unless mat.texture
          apply_colorize_properties(mat, color)
        rescue StandardError => e
          puts("[#{PLUGIN_NAME}] Texture colorize fallback for '#{source.display_name}': #{e.message}")
          mat.color = color
        end
      else
        mat.texture = nil if mat.texture
        mat.color = color
      end

      mat
    rescue StandardError => e
      puts("[#{PLUGIN_NAME}] Failed to create variant '#{source.display_name}' #{hex}: #{e.message}")
      nil
    end


    def copy_texture(source, destination)
      texture = source.texture
      return unless texture

      if texture.respond_to?(:filename) && texture.filename && !texture.filename.empty? && File.exist?(texture.filename)
        destination.texture = texture.filename
      elsif texture.respond_to?(:image_rep)
        image_rep = texture.image_rep
        destination.texture = image_rep if image_rep
      end

      if destination.texture && texture.respond_to?(:size)
        destination.texture.size = texture.size
      end
    end

    def apply_colorize_properties(material, color)
      # For textured materials, setting color turns the texture into a colorized texture.
      # We intentionally avoid forcing colorize_type because that can preserve previous
      # deltas from source materials in some model/material states.
      material.color = color
    end

    def recolor_target_instance(instance, source_materials, variant_material)
      instance.make_unique
      instance.material = variant_material if source_materials.include?(instance.material)
      replace_materials(instance.definition.entities, source_materials, variant_material)
    end

    def replace_materials(entities, source_materials, variant_material)
      entities.grep(Sketchup::Face).each do |face|
        face.material = variant_material if source_materials.include?(face.material)
        face.back_material = variant_material if source_materials.include?(face.back_material)
      end

      nested = entities.grep(Sketchup::Group) + entities.grep(Sketchup::ComponentInstance)
      nested.each do |inst|
        inst.make_unique
        inst.material = variant_material if source_materials.include?(inst.material)
        replace_materials(inst.definition.entities, source_materials, variant_material)
      end
    end

    unless file_loaded?(__FILE__)
      UI.menu('Extensions').add_item(PLUGIN_NAME) { run }
      file_loaded(__FILE__)
    end
  end
end
